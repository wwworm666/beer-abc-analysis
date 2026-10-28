"""Инструкции бота и агентов — из файлов папки kultura_bot.

    prompts/bot.md     инструкции бота (разговор с владельцем в Telegram)
    prompts/agent.md   общая часть инструкций для всех агентов
    agents/<имя>.md    агент: заголовок между строками «---» и текст инструкций

Заголовок агента — строки «ключ: значение»:

    name         латиница, цифры, «_» (имя для ask_agent)
    title        как агента называть в ответах
    domains      разделы сайта через запятую: content, stocks, analytics, staff — инструменты
                 этих разделов (и общие common_) агенту видны, остальные нет
    description  когда поручать задачу этому агенту (бот видит это в своих инструкциях)

Из чего собираются системные промпты (правила сервиса бот берёт у сайта по MCP —
те же, что получают ИИ-агенты владельца, tools.load_catalog):

    бот   = prompts/bot.md + список агентов + правила полного коннектора /mcp
            (instructions из initialize)
    агент = prompts/agent.md + agents/<имя>.md + правила его разделов
            (common_instructions(domain)) + правила полного коннектора

Файлы читаются один раз на процесс: правка инструкций — через выкладку. Ошибка в
заголовке агента — ConfigError с именем файла (tests/test_kultura_bot.py ловит её до
выкладки).
"""
import hashlib
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # kultura_bot/
PROMPTS_DIR = os.path.join(BOT_DIR, 'prompts')
AGENTS_DIR = os.path.join(BOT_DIR, 'agents')

# Разделы сайта (ключи core/mcp/spec.DOMAINS — сверяет tests/test_kultura_bot.py): сервер
# бота кода сайта не содержит, список повторён здесь.
DOMAINS = ('content', 'stocks', 'analytics', 'staff')

AGENT_NAME_RE = re.compile(r'[a-z][a-z0-9_]{1,30}')
REQUIRED_KEYS = ('name', 'title', 'domains', 'description')


class ConfigError(Exception):
    """Файл инструкций с ошибкой: текст называет файл и поле."""


@dataclass(frozen=True)
class AgentDef:
    name: str
    title: str
    domains: Tuple[str, ...]
    description: str
    instructions: str
    path: str


def _read(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read().strip()


def parse_agent(text: str, path: str = '<агент>') -> AgentDef:
    """Разобрать файл агента: заголовок «---» + текст."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        raise ConfigError(f'{path}: файл агента начинается со строки «---» и заголовка')
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == '---')
    except StopIteration:
        raise ConfigError(f'{path}: заголовок не закрыт строкой «---»') from None
    meta: Dict[str, str] = {}
    for n, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        key, sep, value = line.partition(':')
        if not sep:
            raise ConfigError(f'{path}, строка {n}: нужна запись «ключ: значение»')
        meta[key.strip()] = value.strip()
    missing = [k for k in REQUIRED_KEYS if not meta.get(k)]
    if missing:
        raise ConfigError(f'{path}: в заголовке нет {", ".join(missing)}')
    name = meta['name']
    if not AGENT_NAME_RE.fullmatch(name):
        raise ConfigError(f'{path}: name — латиница в нижнем регистре, цифры и «_» (например payroll)')
    domains = tuple(d.strip() for d in meta['domains'].split(',') if d.strip())
    unknown = [d for d in domains if d not in DOMAINS]
    if not domains or unknown:
        raise ConfigError(f'{path}: domains — из {", ".join(DOMAINS)}; неизвестные: {", ".join(unknown) or "—"}')
    body = '\n'.join(lines[end + 1:]).strip()
    if not body:
        raise ConfigError(f'{path}: нет текста инструкций после заголовка')
    return AgentDef(name=name, title=meta['title'], domains=domains, description=meta['description'],
                    instructions=body, path=path)


@lru_cache(maxsize=1)
def load_agents() -> Dict[str, AgentDef]:
    """Агенты из agents/*.md по имени (в порядке имён файлов)."""
    agents: Dict[str, AgentDef] = {}
    for filename in sorted(os.listdir(AGENTS_DIR)):
        if not filename.endswith('.md'):
            continue
        path = os.path.join(AGENTS_DIR, filename)
        agent = parse_agent(_read(path), path=os.path.relpath(path, os.path.dirname(BOT_DIR)))
        if agent.name in agents:
            raise ConfigError(f'{agent.path}: имя {agent.name} уже занято ({agents[agent.name].path})')
        agents[agent.name] = agent
    return agents


@lru_cache(maxsize=1)
def bot_prompt() -> str:
    return _read(os.path.join(PROMPTS_DIR, 'bot.md'))


@lru_cache(maxsize=1)
def agent_prompt() -> str:
    return _read(os.path.join(PROMPTS_DIR, 'agent.md'))


def bot_system_text(service_rules: str) -> str:
    """Системный промпт бота: инструкции, список агентов, правила сервиса (с сайта)."""
    agents = load_agents()
    lines = ['# Агенты для поручений (ask_agent)', '']
    for agent in agents.values():
        lines.append(f'- {agent.name} — {agent.title}: {agent.description}')
    parts = [bot_prompt(), '\n'.join(lines),
             '# Правила сервиса (общие для всех агентов сайта)\n\n' + service_rules.strip()]
    return '\n\n'.join(p.strip() for p in parts if p.strip())


def agent_system_text(agent: AgentDef, domain_rules: List[str], service_rules: str) -> str:
    """Системный промпт агента: общая часть, его инструкции, правила его разделов и сервиса.

    domain_rules — ответы common_instructions(domain) по его разделам (у каждого свой
    заголовок «# Раздел (domain)»)."""
    parts = [agent_prompt(), f'# Ты — агент «{agent.title}»\n\n{agent.instructions}']
    parts += [rules for rules in domain_rules if rules.strip()]
    parts.append('# Правила сервиса (общие для всех агентов сайта)\n\n' + service_rules.strip())
    return '\n\n'.join(p.strip() for p in parts if p.strip())


def fingerprint(system_text: str, tools: List[Dict[str, Any]]) -> str:
    """Отпечаток системного промпта и набора инструментов.

    Сменился (выкладка поменяла инструкции или инструменты) — диалог начинается заново:
    Claude привязывает рассуждения модели к неизменному началу разговора, и старая история
    с новым промптом была бы отвергнута.
    """
    raw = json.dumps({'system': system_text, 'tools': tools}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


DEPLOYED_FILE = '/opt/kultura-bot/deployed'     # коммит main, с которым сервер бота в согласии (пишет update.sh)


def _sha(value: str) -> str:
    value = (value or '').strip().lower()
    return value[:12] if len(value) >= 7 and all(c in '0123456789abcdef' for c in value) else ''


def code_version(repo_dir: str = '', deployed_file: Optional[str] = None) -> str:
    """Коммит, на котором работает сервер бота (первые 12 знаков), или '' — не узнать.

    Сначала — файл DEPLOYED_FILE: update.sh пишет в него коммит main после успешного перезапуска,
    а когда в kultura_bot/ ничего не менялось — сразу (работающий код тот же). Так версия идёт за
    main и после правок только сайта; упал посреди обновления — файл старый, и это видно. Нет
    файла (разработка, тесты) — то, на что указывает .git/HEAD клона, откуда запущен бот; git не
    вызывается: служба работает от своего пользователя, а клон принадлежит root. Читается при
    каждом отчёте сайту (service.report) — страница «Доступ агентов» показывает свежую версию."""
    path = DEPLOYED_FILE if deployed_file is None else deployed_file
    if path:
        try:
            sha = _sha(_read(path))
        except (OSError, UnicodeDecodeError):
            sha = ''
        if sha:
            return sha
    git = os.path.join(repo_dir or os.path.dirname(BOT_DIR), '.git')
    try:
        head = _read(os.path.join(git, 'HEAD')).strip()
        if not head.startswith('ref: '):
            return _sha(head)
        ref = head[5:].strip()
        path = os.path.join(git, *ref.split('/'))
        if os.path.exists(path):
            return _sha(_read(path))
        return _sha(next((line.split()[0] for line in _read(os.path.join(git, 'packed-refs')).splitlines()
                          if line.endswith(' ' + ref)), ''))
    except (OSError, UnicodeDecodeError):
        return ''

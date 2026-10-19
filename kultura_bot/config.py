"""Инструкции бота и агентов — из файлов этой папки.

    prompts/bot.md     инструкции бота (разговор с владельцем в Telegram)
    prompts/agent.md   общая часть инструкций для всех агентов
    agents/<имя>.md    агент: заголовок между строками «---» и текст инструкций

Заголовок агента — строки «ключ: значение»:

    name         латиница, цифры, «_» (имя для ask_agent)
    title        как агента называть в ответах
    domains      разделы сайта через запятую: content, stocks, analytics, staff — инструменты
                 этих разделов (и общие common_) агенту видны, остальные нет
    description  когда поручать задачу этому агенту (бот видит это в своих инструкциях)

Из чего собираются системные промпты:

    бот   = prompts/bot.md + список агентов + правила сервиса для полного коннектора
            (core/mcp/registry.instructions_for(None) — те же, что у агентов по MCP)
    агент = prompts/agent.md + agents/<имя>.md + правила его разделов
            (registry.domain_instructions) + общие правила сервиса

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
from typing import Any, Dict, List, Tuple

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(BOT_DIR, 'prompts')
AGENTS_DIR = os.path.join(BOT_DIR, 'agents')

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
    from core.mcp.spec import DOMAINS
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


def _service_rules(domain=None) -> str:
    from core.mcp import registry
    return registry.instructions_for(domain)


def bot_system_text() -> str:
    """Системный промпт бота: инструкции, список агентов, правила сервиса."""
    agents = load_agents()
    lines = ['# Агенты для поручений (ask_agent)', '']
    for agent in agents.values():
        lines.append(f'- {agent.name} — {agent.title}: {agent.description}')
    parts = [bot_prompt(), '\n'.join(lines),
             '# Правила сервиса (общие для всех агентов сайта)\n\n' + _service_rules(None)]
    return '\n\n'.join(p.strip() for p in parts if p.strip())


def agent_system_text(agent: AgentDef) -> str:
    """Системный промпт агента: общая часть, его инструкции, правила разделов и сервиса."""
    from core.mcp import registry
    from core.mcp.spec import DOMAINS
    parts = [agent_prompt(), f'# Ты — агент «{agent.title}»\n\n{agent.instructions}']
    for domain in agent.domains:
        rules = registry.domain_instructions(domain)
        if rules:
            parts.append(f'# Правила раздела «{DOMAINS[domain].title}» ({domain})\n\n{rules}')
    parts.append('# Правила сервиса (общие для всех агентов сайта)\n\n' + registry.domain_instructions('common'))
    return '\n\n'.join(p.strip() for p in parts if p.strip())


def fingerprint(system_text: str, tools: List[Dict[str, Any]]) -> str:
    """Отпечаток системного промпта и набора инструментов.

    Сменился (выкладка поменяла инструкции или инструменты) — диалог начинается заново:
    Claude привязывает рассуждения модели к неизменному началу разговора, и старая история
    с новым промптом была бы отвергнута.
    """
    raw = json.dumps({'system': system_text, 'tools': tools}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

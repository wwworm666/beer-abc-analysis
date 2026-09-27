"""Реестр MCP-инструментов: собирает описания доменов и раздаёт их коннекторам.

Источники — модули core.mcp.tools.<имя> из MODULES (common + четыре домена).
Каждый экспортирует TOOLS, PROMPTS, INSTRUCTIONS, EXCLUDED (см. core/mcp/tools/__init__.py).

Загрузка терпимая (load): модуль, которого нет или который падает при импорте,
пишет предупреждение в лог и пропускается — остальные домены работают. Это нужно
и на время сборки (домены пишутся параллельно), и в проде: ошибка в одном
описании не должна гасить весь MCP. Такие сбои видны в load_errors(), на странице
«Доступ агентов» и роняют tests/test_mcp_coverage.py.

Проверки при загрузке (инструмент с ошибкой НЕ публикуется):
- spec.validate_tool_spec(spec) пуст;
- домен инструмента совпадает с доменом модуля (common — только в common.py);
- имя уникально среди всех модулей (второй экземпляр отбрасывается).
То же для подсказок (PromptSpec): имя по шаблону, уникальность.

Кому что видно (tools_for):
    None (полный /mcp)  — все инструменты;
    '<домен>'           — инструменты домена + чужие, у которых домен в also_in, + common.
Порядок детерминированный (так требует MCP 2026-07-28 ради кэша клиента): сначала
common, затем домены в порядке spec.DOMAINS, внутри модуля — в порядке объявления.
"""
import importlib
import logging
import threading
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

from core.mcp.spec import (COMMON_DOMAIN, DOMAINS, PROMPT_NAME_RE, PromptSpec, ToolSpec,
                           validate_tool_spec)

log = logging.getLogger('mcp.registry')

MODULES: Tuple[str, ...] = (COMMON_DOMAIN,) + tuple(DOMAINS)
PACKAGE = 'core.mcp.tools'

_lock = threading.RLock()
_state: Optional[Dict[str, Any]] = None
_overrides: Optional[Dict[str, Any]] = None     # тесты: {имя_модуля: модуль или объект}


def use_modules(modules: Optional[Dict[str, Any]]) -> None:
    """Тесты: работать с заданными модулями вместо core.mcp.tools.*. None — вернуть настоящие."""
    global _overrides
    with _lock:
        _overrides = dict(modules) if modules is not None else None
        reset()


def reset() -> None:
    """Забыть загруженное: следующий вызов перечитает модули (тесты, админ-страница)."""
    global _state
    with _lock:
        _state = None


def _import(name: str):
    if _overrides is not None:
        if name not in _overrides:
            raise ImportError(f'модуль {name} не подставлен в тесте')
        return _overrides[name]
    return importlib.import_module(f'{PACKAGE}.{name}')


def load(force: bool = False) -> Dict[str, Any]:
    """Загрузить модули (один раз на процесс; force — заново). Возвращает внутреннее состояние."""
    global _state
    with _lock:
        if _state is not None and not force:
            return _state
        state: Dict[str, Any] = {
            'tools': [], 'by_name': {}, 'prompts': [], 'prompts_by_name': {},
            'instructions': {}, 'excluded': {}, 'excluded_by': {}, 'errors': [], 'modules': [],
        }
        for mod_name in MODULES:
            try:
                module = _import(mod_name)
            except Exception as exc:  # noqa: BLE001 — сломанный модуль не гасит остальные
                message = f'{mod_name}: модуль не загрузился: {type(exc).__name__}: {exc}'
                log.warning('[MCP] %s', message)
                state['errors'].append(message)
                continue
            state['modules'].append(mod_name)
            _collect(state, mod_name, module)
        _state = state
        if state['errors']:
            log.warning('[MCP] реестр загружен с ошибками: %d', len(state['errors']))
        return state


def _collect(state: Dict[str, Any], mod_name: str, module: Any) -> None:
    tools = getattr(module, 'TOOLS', None) or []
    for spec in tools:
        if not isinstance(spec, ToolSpec):
            state['errors'].append(f'{mod_name}: в TOOLS не ToolSpec: {spec!r:.80}')
            continue
        problems = list(validate_tool_spec(spec))
        if spec.domain != mod_name:
            problems.append(f'{spec.name}: домен {spec.domain!r} объявлен в модуле {mod_name}')
        if spec.name in state['by_name']:
            problems.append(f'{spec.name}: имя уже занято в модуле {state["by_name"][spec.name].domain}')
        if problems:
            for problem in problems:
                state['errors'].append(f'{mod_name}: {problem}')
            log.warning('[MCP] инструмент %s не опубликован: %s', spec.name, '; '.join(problems))
            continue
        state['tools'].append(spec)
        state['by_name'][spec.name] = spec

    for prompt in getattr(module, 'PROMPTS', None) or []:
        if not isinstance(prompt, PromptSpec):
            state['errors'].append(f'{mod_name}: в PROMPTS не PromptSpec: {prompt!r:.80}')
            continue
        problems = []
        if not PROMPT_NAME_RE.match(prompt.name or ''):
            problems.append(f'подсказка {prompt.name!r}: имя не подходит под {PROMPT_NAME_RE.pattern}')
        if prompt.domain != mod_name:
            problems.append(f'подсказка {prompt.name}: домен {prompt.domain!r} объявлен в модуле {mod_name}')
        if prompt.name in state['prompts_by_name']:
            problems.append(f'подсказка {prompt.name}: имя уже занято')
        if not callable(prompt.render):
            problems.append(f'подсказка {prompt.name}: render не функция')
        if problems:
            state['errors'].extend(f'{mod_name}: {p}' for p in problems)
            continue
        state['prompts'].append(prompt)
        state['prompts_by_name'][prompt.name] = prompt

    text = getattr(module, 'INSTRUCTIONS', '') or ''
    state['instructions'][mod_name] = text.strip() if isinstance(text, str) else ''

    excluded = getattr(module, 'EXCLUDED', None) or {}
    if not isinstance(excluded, dict):
        state['errors'].append(f'{mod_name}: EXCLUDED должен быть словарём')
        return
    for key, reason in excluded.items():
        if (not isinstance(key, tuple) or len(key) != 2 or not all(isinstance(k, str) for k in key)):
            state['errors'].append(f'{mod_name}: ключ EXCLUDED не (метод, правило): {key!r}')
            continue
        key = (key[0].upper(), key[1])
        if not str(reason or '').strip():
            state['errors'].append(f'{mod_name}: исключение {key} без причины')
            continue
        if key in state['excluded']:
            state['errors'].append(f'{mod_name}: исключение {key} уже объявлено в {state["excluded_by"][key]}')
            continue
        state['excluded'][key] = str(reason).strip()
        state['excluded_by'][key] = mod_name


# ------------------------------------------------------------------- доступ к реестру

def all_tools() -> List[ToolSpec]:
    return list(load()['tools'])


def get_tool(name: str) -> Optional[ToolSpec]:
    return load()['by_name'].get(name)


def tools_for(domain: Optional[str]) -> List[ToolSpec]:
    """Инструменты коннектора (правило — в докстринге модуля)."""
    tools = load()['tools']
    if domain is None:
        return list(tools)
    return [t for t in tools if t.domain in (domain, COMMON_DOMAIN) or domain in t.also_in]


def tool_visible(spec: ToolSpec, domain: Optional[str]) -> bool:
    return domain is None or spec.domain in (domain, COMMON_DOMAIN) or domain in spec.also_in


def prompts_for(domain: Optional[str]) -> List[PromptSpec]:
    prompts = load()['prompts']
    if domain is None:
        return list(prompts)
    return [p for p in prompts if p.domain in (domain, COMMON_DOMAIN)]


def get_prompt(name: str) -> Optional[PromptSpec]:
    return load()['prompts_by_name'].get(name)


def domain_instructions(domain: str) -> str:
    """INSTRUCTIONS одного модуля ('' — нет или модуль не загрузился)."""
    return load()['instructions'].get(domain, '')


def instructions_for(domain: Optional[str]) -> str:
    """Текст instructions для initialize / server/discover.

    Домен: общие правила (common.INSTRUCTIONS) + правила домена.
    Полный /mcp: общие правила + краткая сводка доменов; подробные правила домена
    агент берёт инструментом common_instructions(domain).
    """
    state = load()
    parts = []
    common = state['instructions'].get(COMMON_DOMAIN, '')
    if common:
        parts.append(common)
    if domain is not None:
        own = state['instructions'].get(domain, '')
        if own:
            parts.append(own)
        return '\n\n'.join(parts)
    lines = ['Разделы сервиса (в полном коннекторе доступны все):']
    for key, dom in DOMAINS.items():
        count = sum(1 for t in state['tools'] if t.domain == key)
        lines.append(f'- {dom.title} ({key}, {count} инстр.): {dom.summary} '
                     f'Правила раздела — common_instructions(domain="{key}").')
    parts.append('\n'.join(lines))
    return '\n\n'.join(parts)


def exclusions() -> Dict[Tuple[str, str], str]:
    """(метод, правило Flask) -> причина: объединение EXCLUDED всех модулей."""
    return dict(load()['excluded'])


def exclusion_owner(key: Tuple[str, str]) -> Optional[str]:
    return load()['excluded_by'].get(key)


def load_errors() -> List[str]:
    """Ошибки последней загрузки (пустой список — всё опубликовано)."""
    return list(load()['errors'])


def loaded_modules() -> List[str]:
    return list(load()['modules'])


def summary() -> List[Dict[str, Any]]:
    """Сводка коннекторов для страницы доступа: путь, заголовок, число инструментов."""
    out = [{'domain': None, 'path': '/mcp', 'title': 'Все разделы', 'tools': len(tools_for(None)),
            'prompts': len(prompts_for(None))}]
    for key, dom in DOMAINS.items():
        out.append({'domain': key, 'path': dom.connector_path, 'title': dom.title,
                    'tools': len(tools_for(key)), 'prompts': len(prompts_for(key))})
    return out


def module_from_parts(tools=(), prompts=(), instructions: str = '', excluded=None) -> ModuleType:
    """Тесты: собрать объект-модуль домена из частей (для use_modules)."""
    module = ModuleType('mcp_test_module')
    module.TOOLS = list(tools)
    module.PROMPTS = list(prompts)
    module.INSTRUCTIONS = instructions
    module.EXCLUDED = dict(excluded or {})
    return module

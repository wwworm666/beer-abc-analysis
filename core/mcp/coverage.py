"""Охват MCP: всё, что есть в API сайта, доступно агенту или исключено с причиной.

Правило (решение владельца 2026-09-27 «весь интерфейс и все данные — по MCP»,
контракт 4.9):
- охват — каждое правило Flask с путём '/api/…' плюс NON_API_DATA_ROUTES (фиды и
  календарь: данные, которые отдаются не под /api/);
- для каждой пары (метод из COVERED_METHODS, правило) — РОВНО ОДИН инструмент с тем же
  method и path ИЛИ запись в EXCLUDED одного из модулей (registry.exclusions());
- ни один инструмент не ссылается на несуществующий маршрут или неразрешённый метод,
  его path_params совпадают с аргументами правила;
- исключения не ссылаются на несуществующие маршруты и не спорят с инструментами;
- имена уникальны, validate_tool_spec пуст (иначе реестр инструмент не публикует —
  это load_errors), примеры (examples) проходят schema_check.
Проверяется на голом Flask со ВСЕМИ blueprint'ами сервиса (routes.register_blueprints +
mcp + mcp_oauth) — тот же набор маршрутов, что видит прод (app.py добавляет только
/static/manifest.json). Страницы (HTML) в охват не входят.

Отчёт (check -> CoverageReport) группирует непокрытое по файлам маршрутов — чтобы
было видно, чей это домен (разделы 3 и 5 контракта).
"""
import inspect
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core.mcp import registry, schema_check

NON_API_DATA_ROUTES: Tuple[str, ...] = ('/feeds/taplist.yml', '/feeds/kitchen.yml',
                                        '/feeds/kitchen/<bar_id>', '/schedule/cal.ics')
COVERED_METHODS: Tuple[str, ...] = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

Pair = Tuple[str, str]


def build_full_app():
    """Голый Flask со всеми blueprint'ами сервиса (без app.py: там шедулеры и боты)."""
    from flask import Flask
    from routes import register_blueprints
    app = Flask('mcp_coverage', template_folder=os.path.join(REPO_ROOT, 'templates'),
                static_folder=os.path.join(REPO_ROOT, 'static'))
    register_blueprints(app)
    if 'mcp' not in app.blueprints:
        from routes.mcp import mcp_bp
        app.register_blueprint(mcp_bp)
    if 'mcp_oauth' not in app.blueprints:
        try:
            from routes.mcp_oauth import mcp_oauth_bp
        except ImportError:
            mcp_oauth_bp = None
        if mcp_oauth_bp is not None:
            app.register_blueprint(mcp_oauth_bp)
    return app


def _route_file(app, endpoint: str) -> str:
    view = app.view_functions.get(endpoint)
    try:
        path = inspect.getsourcefile(inspect.unwrap(view))
    except (TypeError, OSError):
        return '?'
    if not path:
        return '?'
    try:
        return os.path.relpath(path, REPO_ROOT).replace(os.sep, '/')
    except ValueError:
        return path


def rule_index(app) -> Dict[str, Dict[str, object]]:
    """rule -> {'methods': {...}, 'endpoint', 'file', 'arguments'} для всех правил приложения."""
    out: Dict[str, Dict[str, object]] = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        entry = out.setdefault(rule.rule, {'methods': set(), 'endpoint': rule.endpoint,
                                           'file': _route_file(app, rule.endpoint),
                                           'arguments': set(rule.arguments)})
        entry['methods'] |= {m for m in rule.methods if m in COVERED_METHODS}
    return out


def required_pairs(app) -> Dict[Pair, str]:
    """(метод, правило) в охвате -> файл маршрута."""
    out: Dict[Pair, str] = {}
    for rule, info in rule_index(app).items():
        if not (rule.startswith('/api/') or rule in NON_API_DATA_ROUTES):
            continue
        for method in sorted(info['methods']):
            out[(method, rule)] = str(info['file'])
    return out


@dataclass
class CoverageReport:
    required: Dict[Pair, str] = field(default_factory=dict)
    uncovered: Dict[str, List[Pair]] = field(default_factory=dict)     # файл -> пары
    duplicates: Dict[Pair, List[str]] = field(default_factory=dict)    # пара -> инструменты
    conflicts: List[str] = field(default_factory=list)                 # и инструмент, и исключение
    dangling_tools: List[str] = field(default_factory=list)
    dangling_exclusions: List[str] = field(default_factory=list)
    path_param_errors: List[str] = field(default_factory=list)
    example_errors: List[str] = field(default_factory=list)
    load_errors: List[str] = field(default_factory=list)
    tools_total: int = 0
    covered_by_tools: int = 0
    covered_by_exclusions: int = 0

    @property
    def uncovered_count(self) -> int:
        return sum(len(v) for v in self.uncovered.values())

    def problems(self) -> Dict[str, List[str]]:
        """Все замечания по группам (пустые группы опущены)."""
        groups: Dict[str, List[str]] = {}
        if self.uncovered:
            groups['uncovered'] = [f'{f}: {m} {r}' for f, pairs in sorted(self.uncovered.items()) for m, r in pairs]
        if self.duplicates:
            groups['duplicates'] = [f'{m} {r}: {", ".join(tools)}' for (m, r), tools in sorted(self.duplicates.items())]
        for name in ('conflicts', 'dangling_tools', 'dangling_exclusions', 'path_param_errors',
                     'example_errors', 'load_errors'):
            items = getattr(self, name)
            if items:
                groups[name] = list(items)
        return groups

    def ok(self) -> bool:
        return not self.problems()

    def format_uncovered(self) -> str:
        if not self.uncovered:
            return 'Все пары (метод, правило) покрыты.'
        lines = [f'Не покрыто {self.uncovered_count} пар (метод, правило) — нужен инструмент или '
                 f'запись в EXCLUDED с причиной:']
        for path in sorted(self.uncovered):
            lines.append(f'  {path}:')
            for method, rule in self.uncovered[path]:
                lines.append(f'    {method:6} {rule}')
        return '\n'.join(lines)

    def format(self) -> str:
        titles = {
            'uncovered': 'Не покрыто', 'duplicates': 'Пара описана несколькими инструментами',
            'conflicts': 'И инструмент, и исключение', 'dangling_tools': 'Инструмент без маршрута',
            'dangling_exclusions': 'Исключение без маршрута', 'path_param_errors': 'Параметры пути',
            'example_errors': 'Примеры не проходят схему', 'load_errors': 'Ошибки загрузки реестра',
        }
        lines = [f'Охват MCP: пар {len(self.required)}, инструментами {self.covered_by_tools}, '
                 f'исключениями {self.covered_by_exclusions}, инструментов всего {self.tools_total}.']
        groups = self.problems()
        if 'uncovered' in groups:
            lines.append(self.format_uncovered())
        for key, items in groups.items():
            if key == 'uncovered':
                continue
            lines.append(f'{titles.get(key, key)} ({len(items)}):')
            lines.extend('  ' + item for item in items)
        return '\n'.join(lines)


def check(app=None) -> CoverageReport:
    """Собрать отчёт охвата (app — готовое приложение или build_full_app())."""
    app = app or build_full_app()
    index = rule_index(app)
    report = CoverageReport(required=required_pairs(app))
    report.load_errors = registry.load_errors()
    tools = registry.all_tools()
    report.tools_total = len(tools)
    exclusions = registry.exclusions()

    by_pair: Dict[Pair, List[str]] = {}
    for spec in tools:
        for example in spec.examples:
            errors = schema_check.check(spec.input_schema, example)
            if errors:
                report.example_errors.append(f'{spec.name}: пример {example!r:.120} — ' + '; '.join(errors[:3]))
        if spec.handler is not None:
            continue
        pair = (spec.method.upper(), spec.path)
        info = index.get(spec.path)
        if info is None:
            report.dangling_tools.append(f'{spec.name}: нет маршрута {spec.path}')
            continue
        if pair[0] not in info['methods']:
            report.dangling_tools.append(f'{spec.name}: маршрут {spec.path} не принимает {pair[0]} '
                                         f'(есть: {", ".join(sorted(info["methods"])) or "—"})')
            continue
        if set(spec.path_params) != info['arguments']:
            report.path_param_errors.append(f'{spec.name}: path_params {sorted(spec.path_params)} '
                                            f'!= аргументы правила {sorted(info["arguments"])}')
        by_pair.setdefault(pair, []).append(spec.name)

    for pair, names in by_pair.items():
        if len(names) > 1:
            report.duplicates[pair] = names
        if pair in exclusions:
            report.conflicts.append(f'{pair[0]} {pair[1]}: инструмент {", ".join(names)} и исключение '
                                    f'({registry.exclusion_owner(pair)}: {exclusions[pair]})')

    for (method, rule), reason in exclusions.items():
        info = index.get(rule)
        if info is None or method not in info['methods']:
            report.dangling_exclusions.append(f'{method} {rule} ({registry.exclusion_owner((method, rule))}): '
                                              f'такого маршрута нет')

    uncovered: Dict[str, List[Pair]] = {}
    for pair, path in sorted(report.required.items(), key=lambda kv: (kv[1], kv[0][1], kv[0][0])):
        if pair in by_pair:
            report.covered_by_tools += 1
        elif pair in exclusions:
            report.covered_by_exclusions += 1
        else:
            uncovered.setdefault(path, []).append(pair)
    report.uncovered = uncovered
    return report


def uncovered_pairs(app=None) -> Set[Pair]:
    report = check(app)
    return {pair for pairs in report.uncovered.values() for pair in pairs}


if __name__ == '__main__':      # py -3 -m core.mcp.coverage — отчёт в консоль
    import sys
    result = check()
    print(result.format())
    sys.exit(0 if result.ok() else 1)

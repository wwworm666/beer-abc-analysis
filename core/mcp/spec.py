"""Формат описания инструментов и подсказок MCP, список доменов.

Инструмент (ToolSpec) — это описание одного действия или отчёта веб-сервиса для
ИИ-агента. Почти всегда он опирается на существующий Flask-маршрут (method + path):
мост (core/mcp/bridge.py) исполняет ровно этот маршрут от имени владельца. Так
агент видит те же цифры, что страница, и не нужен второй экземпляр бизнес-логики.
Инструмент без маршрута (handler) — только для служебного: справочник баров,
документация, уведомление владельцу.

Домены = отдельные коннекторы = роли агентов:

    /mcp/content    Контент и отзывы           агент контент-планов
    /mcp/stocks     Остатки, заказы, краны     агент остатков и аналитики
    /mcp/analytics  Продажи, планы, гости      агент остатков и аналитики
    /mcp/staff      Сотрудники и зарплаты      агент по зарплатам
    /mcp            Всё сразу                  общий агент

Общие инструменты (домен common) видны в каждом коннекторе.

Как аргументы вызова попадают в запрос (bridge.py):
    path_params  -> подставляются в path по <имени>
    query_params -> строка запроса ?a=1&b=2
    file_params  -> файлы multipart: значение {filename, content_base64, mime_type}
    остальное    -> тело запроса: JSON (body='json') или форма (body='form'/'multipart');
                    для body='none' лишних аргументов быть не должно.

Имя инструмента: латиница, нижний регистр, цифры и «_», 3..64 символа, с префиксом
домена: stocks_order_board, staff_salary_calculate. Ограничение длины — требование
клиентов Claude к именам инструментов.

Пометки (annotations MCP) говорят клиенту, насколько вызов опасен:
    read_only   — только читает (GET-отчёты);
    destructive — удаляет или необратимо меняет (удаление, отправка, выгрузка);
    idempotent  — повторный вызов с теми же аргументами ничего не меняет;
    open_world  — выходит за пределы сервиса: iiko-синхронизация, Telegram,
                  Google Таблицы, публичные фиды Яндекса;
    heavy       — живой запрос в iiko или долгий расчёт: мост ограничивает число
                  одновременных таких вызовов, чтобы агент не положил iiko.
    draft_write — запись, которая остаётся черновиком внутри сервиса и никуда не
                  уходит без утверждения владельца (создать/поправить черновик
                  материала контент-плана). Разрешена в режиме «чтение и черновики».

Режимы доступа (MODES, решение по итогам проверки безопасности 2026-09-28):
    full  — все инструменты коннектора (живой разговор владельца с агентом);
    draft — только чтение + draft_write (расписания, которые готовят черновики);
    read  — только чтение (дайджесты, проверки по расписанию).
Режим задаёт адрес коннектора (/mcp/<домен>/draft, /mcp/<домен>/read, без
суффикса — full) и сам токен; действует более строгий из двух. Зачем: агент по
расписанию читает тексты гостей и описания — внедрённая в них «команда» не
должна дотянуться до утверждения, отправки или публичных фидов, и запрет держит
сервер, а не только инструкция агенту.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

TOOL_NAME_RE = re.compile(r'^[a-z][a-z0-9_]{2,63}$')
PROMPT_NAME_RE = TOOL_NAME_RE

HTTP_METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
BODY_KINDS = ('json', 'form', 'multipart', 'none')


@dataclass(frozen=True)
class Domain:
    key: str
    title: str
    connector_path: str
    summary: str


DOMAINS: Dict[str, Domain] = {
    'content': Domain('content', 'Контент и отзывы', '/mcp/content',
                      'Контент-план публикаций, бриф сети, отзывы гостей, полоса «Требует внимания»; '
                      'для постов — чтение кранов, меню кухни, фидов Яндекса и сводки гостей.'),
    'stocks': Domain('stocks', 'Остатки, заказы, краны и меню', '/mcp/stocks',
                     'Остатки и доска заказа, заказы поставщикам, справочник поставщиков, сроки '
                     'годности, Честный знак, краны и таплист, фиды Яндекса, редактор меню.'),
    'analytics': Domain('analytics', 'Продажи, планы и гости', '/mcp/analytics',
                        'Дашборд и планы выручки, месячный отчёт, фасовка и розлив (ABC/XYZ и '
                        'потери), конструктор отчётов, аналитика гостей и акций.'),
    'staff': Domain('staff', 'Сотрудники, график и зарплаты', '/mcp/staff',
                    'Дашборд сотрудника, KPI и цели, расчёт ЗП, график смен и касса, личный '
                    'кабинет, чистота, температура, проверка открытия баров, аккаунты.'),
}
COMMON_DOMAIN = 'common'
ALL_DOMAIN_KEYS: Tuple[str, ...] = tuple(DOMAINS)

# Режимы доступа от строгого к полному (см. docstring модуля).
MODES: Tuple[str, ...] = ('read', 'draft', 'full')
MODE_TITLES: Dict[str, str] = {
    'read': 'Только чтение',
    'draft': 'Чтение и черновики',
    'full': 'Полный доступ',
}


def stricter_mode(*modes: Optional[str]) -> str:
    """Самый строгий из режимов; None и неизвестные значения считаются 'read'.

    Неизвестное значение — значит, что-то пошло не так (битая запись токена):
    безопаснее урезать права до чтения, чем расширить до полного доступа.
    """
    rank = {m: i for i, m in enumerate(MODES)}
    best = len(MODES) - 1
    for mode in modes:
        best = min(best, rank.get(mode, 0))
    return MODES[best]


def allowed_in_mode(spec: 'ToolSpec', mode: str) -> bool:
    """Можно ли вызывать инструмент в режиме mode (full/draft/read).

    owner_notice (сообщение самому владельцу) разрешено в любом режиме: так агент по
    расписанию присылает итог. Получатель — только чат владельца из настроек, лимит в
    сутки, чужие ссылки вырезаются (core/mcp/tools/common.py) — утечки и фишинга нет.
    """
    if mode == 'full' or spec.owner_notice:
        return True
    if spec.read_only:
        return True
    return mode == 'draft' and spec.draft_write


def mode_rank(mode: Optional[str]) -> int:
    """Порядок режимов: read=0 < draft=1 < full=2; неизвестное — как read."""
    return MODES.index(mode) if mode in MODES else 0


def prompt_allowed_in_mode(prompt: 'PromptSpec', mode: str) -> bool:
    """Сценарий показывается, если режим коннектора не строже нужного сценарию."""
    return mode_rank(mode) >= mode_rank(prompt.mode_required)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    domain: str                                  # ключ DOMAINS или 'common'
    title: str                                   # короткое русское название
    description: str                             # что делает/возвращает, единицы, когда звать
    input_schema: dict                           # JSON Schema объекта аргументов
    method: str = 'GET'                          # метод маршрута
    path: str = ''                               # правило Flask: '/api/taps/<bar_id>/start'
    path_params: Tuple[str, ...] = ()
    query_params: Tuple[str, ...] = ()
    file_params: Tuple[str, ...] = ()
    body: str = 'none'                           # 'json' | 'form' | 'multipart' | 'none'
    read_only: bool = True
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False
    heavy: bool = False
    draft_write: bool = False                    # черновик внутри сервиса: можно в режиме draft
    owner_notice: bool = False                   # сообщение только владельцу: можно в любом режиме
    also_in: Tuple[str, ...] = ()                # другие домены, где инструмент тоже нужен
    examples: Tuple[dict, ...] = ()              # безопасные аргументы для дымовых тестов
    handler: Optional[Callable] = None           # служебный инструмент без маршрута:
                                                 # handler(args: dict, principal) -> dict|str

    @property
    def route_backed(self) -> bool:
        return self.handler is None

    def annotations(self) -> dict:
        """Пометки MCP (tools/list -> annotations)."""
        return {
            'title': self.title,
            'readOnlyHint': self.read_only,
            'destructiveHint': self.destructive,
            'idempotentHint': self.idempotent,
            'openWorldHint': self.open_world,
        }

    def domains(self) -> Tuple[str, ...]:
        return (self.domain,) + tuple(d for d in self.also_in if d != self.domain)


@dataclass(frozen=True)
class PromptArg:
    name: str
    description: str
    required: bool = False


@dataclass(frozen=True)
class PromptSpec:
    """Готовый сценарий для агента (prompts/list в MCP; в Claude Code — слэш-команда).

    render(args) -> текст первого сообщения пользователя. Сценарий только
    формулирует задачу; данные агент берёт инструментами.
    """
    name: str
    domain: str
    title: str
    description: str
    arguments: Tuple[PromptArg, ...] = ()
    render: Callable[[dict], str] = field(default=lambda args: '')
    # Самый строгий режим, в котором сценарий выполним: 'read' — только читает и
    # отвечает текстом; 'draft' — создаёт черновики (план месяца). В более строгом
    # коннекторе сценарий не показывается: иначе агент упрётся в отказ сервера.
    mode_required: str = 'read'


# ---------------------------------------------------------------- проверка описаний

_SCHEMA_TYPES = ('object', 'array', 'string', 'integer', 'number', 'boolean', 'null')


def _check_schema_node(node, where: str, errors: List[str]) -> None:
    if not isinstance(node, dict):
        errors.append(f'{where}: схема должна быть объектом')
        return
    types = node.get('type')
    if types is not None:
        for t in (types if isinstance(types, list) else [types]):
            if t not in _SCHEMA_TYPES:
                errors.append(f'{where}: неизвестный тип {t!r}')
    if 'enum' in node and not isinstance(node['enum'], list):
        errors.append(f'{where}: enum должен быть списком')
    props = node.get('properties')
    if props is not None:
        if not isinstance(props, dict):
            errors.append(f'{where}: properties должен быть объектом')
        else:
            for key, sub in props.items():
                _check_schema_node(sub, f'{where}.{key}', errors)
    if 'items' in node:
        _check_schema_node(node['items'], f'{where}[]', errors)
    required = node.get('required')
    if required is not None:
        if not isinstance(required, list):
            errors.append(f'{where}: required должен быть списком')
        elif props is not None:
            missing = [r for r in required if r not in props]
            if missing:
                errors.append(f'{where}: required без описания в properties: {missing}')


def validate_tool_spec(spec: ToolSpec) -> List[str]:
    """Статическая проверка описания. Пустой список — описание корректно."""
    errors: List[str] = []
    where = spec.name or '<без имени>'
    if not TOOL_NAME_RE.match(spec.name or ''):
        errors.append(f'{where}: имя не подходит под {TOOL_NAME_RE.pattern}')
    if spec.domain != COMMON_DOMAIN and spec.domain not in DOMAINS:
        errors.append(f'{where}: неизвестный домен {spec.domain!r}')
    elif spec.domain != COMMON_DOMAIN and not spec.name.startswith(spec.domain + '_'):
        errors.append(f'{where}: имя должно начинаться с «{spec.domain}_»')
    for d in spec.also_in:
        if d not in DOMAINS:
            errors.append(f'{where}: also_in содержит неизвестный домен {d!r}')
    if not spec.title.strip():
        errors.append(f'{where}: пустой title')
    if len(spec.description.strip()) < 20:
        errors.append(f'{where}: слишком короткое описание')
    schema = spec.input_schema
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        errors.append(f'{where}: input_schema должна быть объектом type=object')
        return errors
    _check_schema_node(schema, f'{where}.input_schema', errors)
    if schema.get('additionalProperties') is not False:
        errors.append(f'{where}: input_schema должна запрещать лишние поля (additionalProperties: false)')
    props = set((schema.get('properties') or {}).keys())
    if spec.route_backed:
        if spec.method not in HTTP_METHODS:
            errors.append(f'{where}: неизвестный метод {spec.method}')
        if not spec.path.startswith('/'):
            errors.append(f'{where}: path должен начинаться с /')
        if spec.body not in BODY_KINDS:
            errors.append(f'{where}: body должен быть одним из {BODY_KINDS}')
        in_path = set(re.findall(r'<(?:[a-z_]+:)?([A-Za-z_][A-Za-z0-9_]*)>', spec.path))
        if in_path != set(spec.path_params):
            errors.append(f'{where}: path_params {sorted(spec.path_params)} не совпадают с path {sorted(in_path)}')
        for group_name, group in (('path_params', spec.path_params), ('query_params', spec.query_params),
                                  ('file_params', spec.file_params)):
            unknown = [p for p in group if p not in props]
            if unknown:
                errors.append(f'{where}: {group_name} без описания в input_schema: {unknown}')
        missing_path = [p for p in spec.path_params if p not in (schema.get('required') or [])]
        if missing_path:
            errors.append(f'{where}: параметры пути должны быть обязательными: {missing_path}')
        if spec.body == 'none':
            routed = set(spec.path_params) | set(spec.query_params) | set(spec.file_params)
            loose = sorted(props - routed)
            if loose:
                errors.append(f'{where}: body=none, но аргументы {loose} некуда передать')
        if spec.file_params and spec.body != 'multipart':
            errors.append(f'{where}: file_params требуют body=multipart')
        if spec.method == 'GET' and not spec.read_only:
            errors.append(f'{where}: GET-инструмент должен быть read_only')
    if spec.read_only and spec.destructive:
        errors.append(f'{where}: read_only и destructive одновременно')
    if spec.draft_write and (spec.read_only or spec.destructive or spec.open_world):
        errors.append(f'{where}: draft_write — только для записи черновика: не read_only, '
                      f'не destructive и не open_world')
    if spec.owner_notice and spec.route_backed:
        errors.append(f'{where}: owner_notice — только служебный инструмент без маршрута (handler)')
    return errors

"""
Тесты описаний MCP-инструментов домена content (core/mcp/tools/content.py).

Self-runnable: `py -3 tests/test_mcp_tools_content.py` (совместимо с pytest).

Приложение — голый Flask со ВСЕМИ blueprint'ами сервиса (routes.register_blueprints),
как видит прод; app.py не импортируется: он запускает шедулеры и Telegram с боевыми
токенами. Данные не читаются и не пишутся — нужен только url_map.

Что проверяется (контракт MCP, раздел 5):
- validate_tool_spec пуст; имена уникальны, с префиксом content_, домен content;
- каждый (метод, путь) есть в url_map, метод разрешён, маршрут из своих файлов;
  path_params совпадают с аргументами правила Flask;
- все API-маршруты routes/content_plan.py и routes/reviews.py покрыты ровно одним
  инструментом или стоят в EXCLUDED (страницы HTML в охват не входят); маршруты
  брифа GET/PUT /api/content-plan/brief (раздел 6 контракта) существуют;
- examples проходят проверку схемы: core/mcp/schema_check.py, если он есть, иначе
  своя минимальная проверка (required, type, enum, additionalProperties, пределы);
- перечисления и пределы схем совпадают с константами кода (core.content_plan,
  core.guest_reviews, core.content_media, routes.content_plan), поля брифа — с
  core.content_brief, если он есть;
- пометки: GET — только чтение, удаления и необратимое — destructive, heavy нет;
  open_world — ровно зафиксированный набор отправки (OPEN_WORLD); примеры есть у всех
  инструментов чтения и нет у записи;
- отправка (2026-09-28): каналы, проверка, тестовое сообщение, «Отправить сейчас»,
  аудитория, zip, учёт правок и compact — через мост, транспорт Telegram поддельный;
- тексты: без эмодзи, описание не длиннее DESCRIPTION_MAX; INSTRUCTIONS — 40..90 строк;
  всё, что названо content_*, существует;
- сценарии: имена, аргументы, render на пустых, верных и кривых аргументах;
- модуль совместим с Python 3.10 (нет f-строк PEP 701).
"""

import io
import os
import re
import sys
import tokenize
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core.mcp import spec as mcp_spec  # noqa: E402
from core.mcp.tools import content  # noqa: E402

OWN_BLUEPRINTS = ('content_plan', 'reviews')
ROUTE_METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
BRIEF_PATH = '/api/content-plan/brief'

_APP = None


def _app():
    """Голый Flask со всеми blueprint'ами сервиса (один раз на процесс)."""
    global _APP
    if _APP is None:
        from flask import Flask
        from routes import register_blueprints
        app = Flask(__name__)
        register_blueprints(app)
        _APP = app
    return _APP


def _routes():
    """{(метод, правило): [Rule]} без HEAD/OPTIONS."""
    out = {}
    for rule in _app().url_map.iter_rules():
        for method in rule.methods or ():
            if method in ROUTE_METHODS:
                out.setdefault((method, rule.rule), []).append(rule)
    return out


def _own_api_routes():
    """(метод, правило) API-маршрутов своих файлов (страницы HTML — не /api/)."""
    pairs = set()
    for (method, path), rules in _routes().items():
        if not path.startswith('/api/'):
            continue
        if any(rule.endpoint.split('.')[0] in OWN_BLUEPRINTS for rule in rules):
            pairs.add((method, path))
    return pairs


def _tools():
    return {spec.name: spec for spec in content.TOOLS}


# --------------------------------------------------------------------------- проверка схемы

_JSON_TYPES = {
    'string': lambda v: isinstance(v, str),
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
    'null': lambda v: v is None,
}


def _fallback_check(schema, value, where='args'):
    """Минимальная проверка значения по JSON Schema (подмножество, которым пользуются описания)."""
    errors = []
    types = schema.get('type')
    if types is not None:
        types = types if isinstance(types, list) else [types]
        if not any(_JSON_TYPES[t](value) for t in types):
            return [where + ': тип не ' + '/'.join(types)]
    if 'enum' in schema and value not in schema['enum']:
        errors.append(where + ': значение не из enum')
    if isinstance(value, str):
        if 'minLength' in schema and len(value) < schema['minLength']:
            errors.append(where + ': короче minLength')
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            errors.append(where + ': длиннее maxLength')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(where + ': не подходит под pattern')
        if schema.get('format') == 'date':
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(where + ': такой даты нет')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 'minimum' in schema and value < schema['minimum']:
            errors.append(where + ': меньше minimum')
        if 'maximum' in schema and value > schema['maximum']:
            errors.append(where + ': больше maximum')
    if isinstance(value, list):
        if 'minItems' in schema and len(value) < schema['minItems']:
            errors.append(where + ': меньше minItems')
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            errors.append(where + ': больше maxItems')
        if 'items' in schema:
            for i, item in enumerate(value):
                errors += _fallback_check(schema['items'], item, where + '[' + str(i) + ']')
    if isinstance(value, dict):
        props = schema.get('properties') or {}
        for key in schema.get('required') or []:
            if key not in value:
                errors.append(where + ': нет обязательного ' + key)
        for key, item in value.items():
            if key in props:
                errors += _fallback_check(props[key], item, where + '.' + key)
            elif schema.get('additionalProperties') is False:
                errors.append(where + ': лишнее поле ' + key)
    return errors


def _real_check(schema, args):
    """Ошибки по core/mcp/schema_check.check (им протокол проверяет вызовы) или None — модуля ещё нет."""
    try:
        from core.mcp import schema_check
    except ImportError:
        return None
    return [str(e) for e in schema_check.check(schema, args)]


def _schema_errors(schema, args):
    """Ошибки аргументов: своя минимальная проверка плюс core/mcp/schema_check, если он есть."""
    return _fallback_check(schema, args) + (_real_check(schema, args) or [])


# --------------------------------------------------------------------------- эмодзи

_EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]')


def _texts():
    """Все тексты домена, которые видит агент: (где, текст)."""
    out = [('INSTRUCTIONS', content.INSTRUCTIONS)]
    for spec in content.TOOLS:
        out.append((spec.name + '.title', spec.title))
        out.append((spec.name + '.description', spec.description))
        out.append((spec.name + '.schema', repr(spec.input_schema)))
    for prompt in content.PROMPTS:
        out.append((prompt.name + '.title', prompt.title))
        out.append((prompt.name + '.description', prompt.description))
        for arg in prompt.arguments:
            out.append((prompt.name + '.' + arg.name, arg.description))
    return out


# --------------------------------------------------------------------------- тесты: описания

def test_specs_valid():
    errors = [e for spec in content.TOOLS for e in mcp_spec.validate_tool_spec(spec)]
    assert errors == [], errors


def test_names_unique_prefixed():
    names = [spec.name for spec in content.TOOLS]
    assert len(names) == len(set(names)), 'повтор имени инструмента'
    for spec in content.TOOLS:
        assert spec.domain == 'content', spec.name
        assert spec.name.startswith('content_'), spec.name
        assert mcp_spec.TOOL_NAME_RE.match(spec.name), spec.name
        assert spec.route_backed, spec.name + ': у домена content только инструменты-маршруты'
        for other in spec.also_in:
            assert other in mcp_spec.DOMAINS, spec.name


def test_exports():
    assert isinstance(content.TOOLS, list) and content.TOOLS
    assert isinstance(content.PROMPTS, list) and content.PROMPTS
    assert isinstance(content.INSTRUCTIONS, str) and content.INSTRUCTIONS.strip()
    assert isinstance(content.EXCLUDED, dict)
    for key, reason in content.EXCLUDED.items():
        assert isinstance(key, tuple) and len(key) == 2, key
        assert isinstance(reason, str) and reason.strip(), key


# --------------------------------------------------------------------------- тесты: маршруты

def test_routes_exist_and_params_match():
    routes = _routes()
    for spec in content.TOOLS:
        key = (spec.method, spec.path)
        assert key in routes, spec.name + ': нет маршрута ' + spec.method + ' ' + spec.path
        rules = routes[key]
        assert any(rule.endpoint.split('.')[0] in OWN_BLUEPRINTS for rule in rules), \
            spec.name + ': маршрут не из routes/content_plan.py или routes/reviews.py'
        for rule in rules:
            assert set(rule.arguments) == set(spec.path_params), \
                spec.name + ': path_params ' + repr(spec.path_params) + ' != ' + repr(sorted(rule.arguments))


def test_brief_routes_exist():
    """GET/PUT брифа пишет агент G (раздел 6 контракта) — без них инструменты брифа мёртвые."""
    routes = _routes()
    missing = [m for m in ('GET', 'PUT') if (m, BRIEF_PATH) not in routes]
    assert not missing, 'нет маршрутов брифа: ' + ', '.join(m + ' ' + BRIEF_PATH for m in missing)


def test_all_own_routes_covered_once():
    covered = {}
    for spec in content.TOOLS:
        covered.setdefault((spec.method, spec.path), []).append(spec.name)
    doubles = {key: names for key, names in covered.items() if len(names) > 1}
    assert not doubles, 'маршрут описан дважды: ' + repr(doubles)
    own = _own_api_routes()
    missing = sorted(key for key in own if key not in covered and key not in content.EXCLUDED)
    assert not missing, 'маршруты без инструмента и без EXCLUDED: ' + repr(missing)
    both = sorted(key for key in covered if key in content.EXCLUDED)
    assert not both, 'маршрут и описан, и исключён: ' + repr(both)
    foreign = sorted(key for key in content.EXCLUDED if key not in own)
    assert not foreign, 'EXCLUDED содержит чужие или несуществующие маршруты: ' + repr(foreign)


# --------------------------------------------------------------------------- тесты: схемы и примеры

def test_examples_pass_schema():
    for spec in content.TOOLS:
        for example in spec.examples:
            errors = _schema_errors(spec.input_schema, example)
            assert errors == [], spec.name + ': ' + repr(errors)


def test_examples_policy():
    for spec in content.TOOLS:
        if spec.read_only and not spec.heavy:
            assert spec.examples, spec.name + ': у инструмента чтения нужен пример для дымового теста'
        if not spec.read_only:
            assert not spec.examples, spec.name + ': у записи примеров быть не должно (дымовой прогон)'


def test_bad_args_rejected_by_schema():
    """Схема ловит типичные ошибки агента до вызова маршрута."""
    tools = _tools()
    cases = [
        ('content_placements_add', {'material_id': 'm_1', 'channel': 'vk'}),
        ('content_placements_add', {'material_id': 'm_1', 'channel': 'telegram', 'bar': 'bolshoy'}),
        ('content_material_create', {'month': '2026-11'}),
        ('content_material_update', {'material_id': 'm_1', 'month': '2026-11'}),
        ('content_placement_action', {'placement_id': 'p_1', 'action': 'publish'}),
        ('content_material_shift', {'material_id': 'm_1', 'days': 61}),
        ('content_material_repeat', {'material_id': 'm_1', 'weekdays': [7]}),
        ('content_reviews_list', {'rating': 'good'}),
        ('content_review_add', {'source': 'yandex', 'bar': 'all', 'rating': 5}),
        ('content_review_add', {'source': 'yandex', 'bar': 'bolshoy', 'rating': 6}),
        ('content_approve', {'placement_ids': []}),
        ('content_brief_update', {'sections': {'slogan': 'x'}}),
        ('content_brief_update', {'sections': {'bars': {'nevsky': {'character': 'x'}}}}),
        ('content_media_upload', {'material_id': 'm_1', 'file': {'filename': 'a.jpg'}}),
        ('content_live_preview', {'bar': 'bolshoy', 'date': '2026-02-30'}),
        ('content_reviews_list', {'from': '2026-9-1'}),
        ('content_media_get', {'name': '../secret.jpg'}),
    ]
    for name, args in cases:
        schema = tools[name].input_schema
        assert _fallback_check(schema, args), name + ': схема пропустила ' + repr(args)
        real = _real_check(schema, args)
        assert real is None or real, name + ': schema_check пропустил ' + repr(args)


def _prop(tool, *path):
    node = _tools()[tool].input_schema
    for key in path:
        node = node['properties'][key] if key != '[]' else node['items']
    return node


def test_enums_and_limits_match_code():
    import core.content_media as cm
    import core.content_plan as cp
    import core.guest_reviews as gr
    import routes.content_plan as rcp

    assert content.BAR_KEYS == cp.BAR_KEYS == gr.BAR_KEYS
    assert content.BAR_ALL == cp.BAR_ALL == gr.NETWORK_BAR
    assert content.CHANNELS == cp.CHANNEL_ORDER and set(content.CHANNELS) == set(cp.CHANNELS)
    assert content.AUDIENCES == tuple(a['key'] for a in cp.AUDIENCES)
    assert content.KINDS == cp.KINDS
    assert content.LIVE_SOURCES == tuple(cp.LIVE_SOURCES)
    assert content.PLACEHOLDERS == cp.PLACEHOLDERS
    assert set(content.PLACEMENT_ACTIONS) == set(cp.ACTIONS)
    assert content.CROSS_MONTH_STATES == cp.CROSS_MONTH_STATES
    assert content.BULK_ACTIONS == rcp.BULK_ACTIONS
    assert content.BULK_MAX == rcp.BULK_MAX
    assert (content.TITLE_MAX, content.TEXT_MAX, content.NOTE_MAX) == (cp.TITLE_MAX, cp.TEXT_MAX, cp.NOTE_MAX)
    assert content.SHIFT_DAYS_MAX == cp.SHIFT_DAYS_MAX
    assert content.MATERIAL_MEDIA_MAX == cp.MATERIAL_MEDIA_MAX
    assert (content.TG_TEXT_LIMIT, content.TG_CAPTION_LIMIT, content.IG_CAPTION_LIMIT) == \
        (cp.TG_TEXT_LIMIT, cp.TG_CAPTION_LIMIT, cp.IG_CAPTION_LIMIT)
    assert content.MEDIA_MAX == cp.TG_MEDIA_MAX == cp.IG_MEDIA_MAX
    assert content.MEDIA_NAME_PATTERN[:-1] + '\\Z' == cm.NAME_RE.pattern
    import core.content_channels as cc
    assert content.AGENT_EDITS_MONTHS_MAX == cp.AGENT_EDITS_MONTHS_MAX
    assert content.REMINDER_MINUTES_MAX == cc.REMINDER_MINUTES_MAX
    assert content.CHANNEL_TITLE_MAX == cc.TITLE_MAX
    assert _prop('content_agent_edits', 'months')['maximum'] == cp.AGENT_EDITS_MONTHS_MAX
    assert _prop('content_audience', 'segment')['enum'] == list(content.AUDIENCES)
    assert _prop('content_channels_update', 'instagram', 'reminder_minutes_before')['maximum'] == \
        cc.REMINDER_MINUTES_MAX
    assert tuple(_prop('content_channels_update', 'telegram')['properties']) == cp.BAR_KEYS
    assert tuple(_prop('content_channels_update', 'telegram', 'bolshoy')['properties']) == cc.BAR_FIELDS
    assert tuple(_prop('content_channels_update', 'instagram')['properties']) == cc.INSTAGRAM_FIELDS
    assert tuple(_prop('content_channels_update', 'bot')['properties']) == cc.BOT_FIELDS
    assert set(_tools()['content_channels_update'].input_schema['properties']) == set(cc.TOP_KEYS)
    # новые поля материала (раздел 6 контракта): пределы, если хранилище их объявило
    for attr in ('AGENT_RATIONALE_MAX', 'SHOT_LIST_MAX', 'AGENT_TEXT_MAX'):
        if hasattr(cp, attr):
            assert getattr(cp, attr) == content.AGENT_TEXT_MAX, attr

    assert content.REVIEW_SOURCES == gr.SOURCE_KEYS
    assert content.REVIEW_STATUSES == gr.STATUSES
    assert content.RATING_FILTERS == gr.RATING_FILTERS
    assert (content.RATING_MIN, content.RATING_MAX) == (gr.RATING_MIN, gr.RATING_MAX)
    assert (content.MAX_AUTHOR_LEN, content.MAX_REVIEW_TEXT_LEN, content.MAX_REPLY_LEN,
            content.MAX_SKIP_REASON_LEN, content.MAX_PHONE_LEN, content.MAX_TELEGRAM_LEN) == \
        (gr.MAX_AUTHOR_LEN, gr.MAX_TEXT_LEN, gr.MAX_REPLY_LEN, gr.MAX_SKIP_REASON_LEN,
         gr.MAX_PHONE_LEN, gr.MAX_TELEGRAM_LEN)

    # схемы действительно используют эти значения
    assert _prop('content_placements_add', 'channel')['enum'] == list(content.CHANNELS)
    assert _prop('content_placements_add', 'audience')['enum'] == list(content.AUDIENCES)
    assert _prop('content_placements_add', 'bars', '[]')['enum'] == list(content.BAR_KEYS_ALL)
    assert _prop('content_placement_action', 'action')['enum'] == list(content.PLACEMENT_ACTIONS)
    assert _prop('content_material_create', 'kind')['enum'] == list(content.KINDS)
    assert _prop('content_material_create', 'title')['maxLength'] == cp.TITLE_MAX
    assert _prop('content_material_create', 'base_text')['maxLength'] == cp.TEXT_MAX
    assert _prop('content_materials_bulk', 'action')['enum'] == list(rcp.BULK_ACTIONS)
    assert _prop('content_materials_bulk', 'material_ids')['maxItems'] == rcp.BULK_MAX
    assert _prop('content_review_add', 'bar')['enum'] == list(gr.BAR_KEYS)
    assert _prop('content_review_reply', 'text')['maxLength'] == gr.MAX_REPLY_LEN


def test_material_fields_match_store():
    """Поля create/patch = редактируемые поля хранилища (+ month у создания) без служебных."""
    import core.content_plan as cp
    create = set(_tools()['content_material_create'].input_schema['properties'])
    patch = set(_tools()['content_material_update'].input_schema['properties']) - {'material_id'}
    editable = set(cp.MATERIAL_EDITABLE) | {'agent_rationale', 'shot_list'}
    assert patch == editable, sorted(patch ^ editable)
    assert create == editable | {'month'}, sorted(create ^ (editable | {'month'}))
    placement = set(_tools()['content_placement_update'].input_schema['properties']) - {'placement_id'}
    assert placement == set(cp.PLACEMENT_EDITABLE), sorted(placement ^ set(cp.PLACEMENT_EDITABLE))


def test_review_fields_match_store():
    import core.guest_reviews as gr
    patch = set(_tools()['content_review_update'].input_schema['properties']) - {'review_id'}
    assert patch == set(gr.ReviewStore.EDITABLE_FIELDS), sorted(patch ^ set(gr.ReviewStore.EDITABLE_FIELDS))
    add = set(_tools()['content_review_add'].input_schema['properties'])
    assert add == set(gr.ReviewStore.EDITABLE_FIELDS), sorted(add ^ set(gr.ReviewStore.EDITABLE_FIELDS))


def test_brief_schema_matches_store():
    """Поля и пределы брифа = core/content_brief.py (раздел 6 контракта)."""
    from core import content_brief as cb
    sections = _tools()['content_brief_update'].input_schema['properties']['sections']['properties']
    text_keys = tuple(key for key, _text in content.BRIEF_TEXT_SECTIONS)
    bar_fields = tuple(key for key, _text in content.BRIEF_BAR_FIELDS)
    assert text_keys == cb.TEXT_KEYS
    assert bar_fields == cb.BAR_FIELD_KEYS
    assert set(sections) == set(cb.SECTION_KEYS)
    bars = sections['bars']['properties']
    assert tuple(bars) == content.BAR_KEYS == cb.BAR_KEYS
    for bar in content.BAR_KEYS:
        assert tuple(bars[bar]['properties']) == cb.BAR_FIELD_KEYS
        for field in cb.BAR_FIELD_KEYS:
            assert bars[bar]['properties'][field]['maxLength'] == cb.BAR_FIELD_MAX
    for key in cb.TEXT_KEYS:
        assert sections[key]['maxLength'] == cb.SECTION_TEXT_MAX, key
    assert sections['examples']['maxItems'] == cb.EXAMPLES_MAX
    assert sections['examples']['items']['maxLength'] == cb.EXAMPLE_TEXT_MAX
    assert (content.BRIEF_SECTION_MAX, content.BRIEF_EXAMPLE_MAX, content.BRIEF_EXAMPLES_MAX,
            content.BRIEF_BAR_FIELD_MAX, content.BRIEF_TOTAL_MAX) == \
        (cb.SECTION_TEXT_MAX, cb.EXAMPLE_TEXT_MAX, cb.EXAMPLES_MAX, cb.BAR_FIELD_MAX, cb.BRIEF_TOTAL_MAX)
    # PUT принимает то, что описывает схема: пример из схемы проходит проверку хранилища
    patch = {'sections': {'tone': 'На «вы».', 'examples': ['Пример поста'], 'notes': None,
                          'bars': {'ligovskiy': {'hours': '12:00–02:00'}}}}
    assert _schema_errors(_tools()['content_brief_update'].input_schema, patch) == []
    assert cb.clean_patch(patch)['bars'] == {'ligovskiy': {'hours': '12:00–02:00'}}


def test_agent_fields_match_store():
    """origin (раздел 6): в теле запрещён сервером — и схемой; фильтр approve-preview — те же значения."""
    import core.content_plan as cp
    assert content.ORIGINS == cp.ORIGINS
    assert content.AGENT_TEXT_MAX == cp.AGENT_TEXT_MAX
    tools = _tools()
    for name in ('content_material_create', 'content_material_update'):
        props = tools[name].input_schema['properties']
        assert 'origin' not in props, name
        assert props['agent_rationale']['maxLength'] == cp.AGENT_TEXT_MAX
        assert props['shot_list']['maxLength'] == cp.AGENT_TEXT_MAX
    assert _prop('content_approve_preview', 'origin')['enum'] == list(cp.ORIGINS)
    drafts = tools['content_agent_drafts_delete']
    assert drafts.destructive and drafts.input_schema['required'] == ['month']
    assert drafts.input_schema['properties']['material_ids']['maxItems'] == content.BULK_MAX


# --------------------------------------------------------------------------- тесты: пометки

# Выход в Telegram или разрешение выхода (2026-09-28): утверждение и повтор отправки
# ставят публикацию в очередь, выключатель включает отправку, проверка канала ходит в
# Telegram, тестовое сообщение и «Отправить сейчас» пишут в канал.
OPEN_WORLD = {'content_approve', 'content_placement_action', 'content_channels_update',
              'content_channel_check', 'content_channel_test', 'content_publish_now',
              'content_review_send_reply', 'content_bulk_pause'}   # снятие паузы выпускает посты
DESTRUCTIVE = {'content_approve', 'content_placement_action', 'content_materials_bulk', 'content_media_delete',
               'content_material_delete', 'content_placement_delete', 'content_review_delete',
               'content_agent_drafts_delete', 'content_channels_update', 'content_channel_test',
               'content_publish_now', 'content_review_send_reply'}


def test_annotations():
    tools = _tools()
    for spec in content.TOOLS:
        assert not spec.heavy, spec.name + ': контент-план и отзывы не ходят в iiko'
        if spec.method == 'GET':
            assert spec.read_only, spec.name
        if spec.method == 'DELETE':
            assert spec.destructive and not spec.read_only, spec.name
        if spec.read_only:
            assert spec.method in ('GET', 'POST') and not spec.destructive and not spec.open_world, spec.name
        if spec.open_world:
            assert not spec.draft_write, spec.name + ': выход наружу — не черновик'
    assert {t.name for t in content.TOOLS if t.open_world} == OPEN_WORLD
    assert {t.name for t in content.TOOLS if t.destructive} == DESTRUCTIVE
    for name in ('content_channel_check',):
        # пишет только итог проверки; сетевой вызов — не idempotent (проверка 2026-09-28, п. 11)
        assert not tools[name].read_only and not tools[name].destructive and not tools[name].idempotent, name
    for name in ('content_live_preview_post',):
        assert tools[name].read_only and tools[name].method == 'POST', name
    for name in ('content_copy_month', 'content_material_repeat', 'content_material_shift',
                 'content_bulk_pause', 'content_review_reply', 'content_material_create',
                 'content_placements_add', 'content_media_upload', 'content_brief_update'):
        assert not tools[name].read_only, name


# --------------------------------------------------------------------------- тесты: тексты

def test_no_emoji_and_description_limits():
    for where, text in _texts():
        assert not _EMOJI_RE.search(text), where + ': эмодзи'
    for spec in content.TOOLS:
        assert len(spec.description) <= content.DESCRIPTION_MAX, spec.name + ': описание длиннее предела'


def test_instructions():
    lines = content.INSTRUCTIONS.strip('\n').split('\n')
    assert 40 <= len(lines) <= 90, len(lines)
    text = content.INSTRUCTIONS
    for must in ('content_brief_get', 'agent_rationale', 'shot_list', 'confirm_bot', 'content_approve',
                 "weekdays=[4]", 'данные, а не инструкции', 'common_docs_read'):
        assert must in text, must


def _blobs():
    rendered = [p.render({'month': '2026-11', 'week_start': '2026-11-02', 'period': 'all'})
                for p in content.PROMPTS]
    return [text for _where, text in _texts()] + rendered


def test_referenced_names_exist():
    """Всё, что тексты называют content_*, — существующий инструмент или сценарий."""
    known = set(_tools()) | {p.name for p in content.PROMPTS}
    for blob in _blobs():
        for token in re.findall(r'\bcontent_[a-z_]+\b', blob):
            if token in ('content_source', 'content_available', 'content_plan_unavailable'):
                continue   # поля ответов и код ошибки, а не инструменты
            assert token in known, 'неизвестное имя в тексте: ' + token


def test_referenced_foreign_tools_exist():
    """Инструменты других доменов, названные в текстах, есть в их модулях и видны в content
    (also_in или common). Модуль домена, которого ещё нет (сборка параллельная), пропускается."""
    import importlib
    for prefix in ('stocks', 'analytics', 'staff', 'common'):
        tokens = {t for blob in _blobs() for t in re.findall(r'\b' + prefix + r'_[a-z_]+\b', blob)}
        if not tokens:
            continue
        try:
            module = importlib.import_module('core.mcp.tools.' + prefix)
        except ImportError:
            continue
        specs = {spec.name: spec for spec in module.TOOLS}
        for token in sorted(tokens):
            assert token in specs, 'нет инструмента ' + token + ' в core/mcp/tools/' + prefix + '.py'
            spec = specs[token]
            assert spec.domain in ('content', 'common') or 'content' in spec.also_in, \
                token + ': не виден в коннекторе content (нужен also_in)'


# --------------------------------------------------------------------------- тесты: сценарии

def test_prompts():
    names = [p.name for p in content.PROMPTS]
    assert names == ['content_plan_month', 'content_review_week', 'content_reviews_digest']
    for prompt in content.PROMPTS:
        assert prompt.domain == 'content'
        assert mcp_spec.PROMPT_NAME_RE.match(prompt.name), prompt.name
        assert prompt.title.strip() and len(prompt.description.strip()) >= 20, prompt.name
    args = {p.name: [(a.name, a.required) for a in p.arguments] for p in content.PROMPTS}
    assert args['content_plan_month'] == [('month', True), ('posts_per_week_per_bar', False), ('focus', False)]
    assert args['content_review_week'] == [('week_start', False)]
    assert args['content_reviews_digest'] == [('period', False)]


def test_prompt_render():
    by_name = {p.name: p for p in content.PROMPTS}
    samples = [{}, {'month': '2026-11', 'posts_per_week_per_bar': '3', 'focus': 'Октоберфест'},
               {'month': 'ноябрь', 'posts_per_week_per_bar': 'часто'}, {'week_start': '2026-11-02'},
               {'week_start': 'завтра'}, {'period': '2026-09'}, {'period': 'all'},
               {'period': '2026-09-01..2026-09-15'}, {'period': 'вчера'}, {'month': None}]
    for prompt in content.PROMPTS:
        for args in samples:
            text = prompt.render(args)
            assert isinstance(text, str) and len(text) > 200, prompt.name + ' ' + repr(args)
            assert 'Формат ответа' in text and 'Шаги' in text, prompt.name
            assert not _EMOJI_RE.search(text), prompt.name
    month = by_name['content_plan_month'].render({'month': '2026-11', 'posts_per_week_per_bar': '3'})
    assert 'ноябрь 2026' in month and "month='2026-11'" in month and '3 пост' in month
    assert 'content_brief_get' in month and 'weekdays=[4]' in month
    assert "content_reviews_list(month='2026-10', rating='high')" in month      # отзывы прошлого месяца
    assert "month='2025-12'" in by_name['content_plan_month'].render({'month': '2026-01'})
    bad = by_name['content_plan_month'].render({'month': 'ноябрь'})
    assert 'уточните' in bad
    week = by_name['content_review_week'].render({'week_start': '2026-11-02'})
    assert '2026-11-02' in week and 'content_approve_preview' in week
    digest = by_name['content_reviews_digest']
    assert "from='2026-09-01', to='2026-09-15'" in digest.render({'period': '2026-09-01..2026-09-15'})
    assert 'all=true' in digest.render({'period': 'all'})
    assert "month='2026-09'" in digest.render({'period': '2026-09'})
    assert 'не распознан' in digest.render({'period': 'вчера'})


# --------------------------------------------------------------------------- тесты: через мост

OWNER = {'id': 1, 'login': 'owner', 'display_name': 'Владелец', 'is_admin': True, 'active': True}
FROZEN_NOW = (2026, 10, 7, 12, 0)     # среда; «сегодня» для хранилищ в тесте моста


class _FakeTelegram:
    """Поддельный транспорт Telegram (в настоящий ничего не уходит): отвечает как Bot API
    на getMe / getChat / getChatMember / sendMessage / загрузку файла и пишет вызовы."""

    token = 'test-token'

    def __init__(self):
        self.calls = []
        self.next_id = 100

    def _mid(self):
        self.next_id += 1
        return self.next_id

    def call(self, method, payload=None):
        self.calls.append((method, dict(payload or {})))
        if method == 'getMe':
            return {'ok': True, 'result': {'id': 42, 'username': 'kult_test_bot'}}
        if method == 'getChat':
            return {'ok': True, 'result': {'id': -1001, 'type': 'channel', 'title': 'Культура ВО',
                                           'username': 'kult_vo'}}
        if method == 'getChatMember':
            return {'ok': True, 'result': {'status': 'administrator', 'can_post_messages': True}}
        return {'ok': True, 'result': {'message_id': self._mid()}}

    def upload(self, method, fields, files):
        self.calls.append((method, dict(fields or {}), [f[0] for f in files]))
        return {'ok': True, 'result': {'message_id': self._mid(), 'photo': [{'file_id': 'F-' + files[0][0]}]}}


class _BridgeRig:
    """Мост core/mcp/bridge.py над голым Flask (content_plan + reviews) и временными
    хранилищами с замороженными часами. Точки подмены — те же, что в
    tests/test_content_plan.py и tests/test_guest_reviews.py; всё возвращается в __exit__.
    current_user() настоящий: пользователя кладёт мост (g._current_user, via_mcp).
    Отправка: настройки каналов во временной папке, транспорт Telegram — _FakeTelegram,
    аудитория бота — 7 подписчиков, фоновая рассылка — синхронно."""

    def __enter__(self):
        import tempfile
        from datetime import datetime
        from flask import Flask
        import core.content_brief as cb
        import core.content_channels as cc
        import core.content_plan as cp
        import core.guest_reviews as gr
        import routes.content_plan as rcp
        import routes.reviews as rrev
        from core.mcp import bridge
        from core.mcp.principal import Principal
        self.bridge = bridge
        self.tmp = tempfile.mkdtemp(prefix='mcp_content_')
        clock = lambda: datetime(*FROZEN_NOW)  # noqa: E731
        plan = cp.ContentPlanStore(os.path.join(self.tmp, 'content_plan.json'), now_fn=clock,
                                   audience_fn=lambda segment, bar: (7, 'тестовые подписчики'))
        reviews = gr.ReviewStore(os.path.join(self.tmp, 'guest_reviews.json'), clock=clock)
        brief = cb.ContentBriefStore(os.path.join(self.tmp, 'content_brief.json'), now_fn=clock)
        channels = cc.ChannelsStore(os.path.join(self.tmp, 'content_channels.json'), now_fn=clock)
        self.telegram = _FakeTelegram()
        self.plan = plan
        self.saved = [(rcp, '_store', rcp._store), (rcp, '_brief_store', rcp._brief_store),
                      (rcp, '_channels', rcp._channels), (rcp, '_transport', rcp._transport),
                      (rcp, '_guest_transport', rcp._guest_transport), (rcp, '_bot_token', rcp._bot_token),
                      (rcp, '_guest_bot_token', rcp._guest_bot_token), (rcp, '_audience', rcp._audience),
                      (rcp, '_subscribers_total', rcp._subscribers_total),
                      (rrev, 'get_review_store', rrev.get_review_store),
                      (rrev, '_content_plan_store', rrev._content_plan_store),
                      (bridge, 'owner_record', bridge.owner_record)]
        rcp._store = lambda: plan
        rcp._brief_store = lambda: brief
        rcp._channels = lambda: channels
        rcp._transport = lambda: self.telegram
        rcp._guest_transport = lambda: self.telegram
        rcp._bot_token = lambda: ('test-token', 'taplist')
        rcp._guest_bot_token = lambda: ('test-token', 'taplist')
        rcp._audience = lambda segment, bar: (7, 'тестовые подписчики')
        rcp._subscribers_total = lambda: 7
        self.channels = channels
        rrev.get_review_store = lambda *a, **k: reviews
        rrev._content_plan_store = lambda: plan
        bridge.owner_record = lambda principal: dict(OWNER, via_mcp=True, mcp_client=principal.client_name,
                                                     mcp_token_id=principal.token_id)
        app = Flask(__name__)
        app.register_blueprint(rcp.content_plan_bp)
        app.register_blueprint(rrev.reviews_bp)
        self.ctx = app.app_context()
        self.ctx.push()
        self.principal = Principal(user_id=1, login='owner', display_name='Владелец', token_id='st_test',
                                   token_kind='static', client_name='pytest')
        return self

    def __exit__(self, *exc):
        import shutil
        self.ctx.pop()
        for module, name, value in self.saved:
            setattr(module, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def call(self, name, args):
        result = self.bridge.execute(_tools()[name], args, self.principal, connector='content')
        return result

    def ok(self, name, args):
        import json
        result = self.call(name, args)
        assert not result.is_error, name + ': ' + result.text_value[:500]
        return json.loads(result.text_value)


def _bridge_available():
    try:
        from core.mcp import bridge  # noqa: F401
        import core.content_brief  # noqa: F401
    except ImportError:
        return False
    return True


def test_bridge_read_examples_no_5xx():
    """Все примеры инструментов чтения проходят мост: без 5xx (404 у выдуманных id — норма)."""
    if not _bridge_available():
        return
    with _BridgeRig() as rig:
        for spec in content.TOOLS:
            if not spec.read_only:
                continue
            for example in spec.examples:
                result = rig.call(spec.name, example)
                assert (result.http_status or 200) < 500, spec.name + ': ' + result.text_value[:300]
                if not result.is_error:
                    assert result.content and result.content[0]['type'] in ('text', 'image'), spec.name


def test_bridge_agent_workflow():
    """Сценарий агента через мост: бриф, живой таплист пятницы, Instagram без фото, серия,
    предпросмотр утверждения «только ИИ», удаление черновиков ИИ, отзыв -> черновик ответа
    -> материал. Проверяет раскладку аргументов (путь/запрос/тело) и пометки агента."""
    if not _bridge_available():
        return
    with _BridgeRig() as rig:
        brief = rig.ok('content_brief_get', {})
        assert brief['stored'] is False and 'bars' in brief['brief']['sections']
        saved = rig.ok('content_brief_update', {'sections': {'tone': 'На «вы».',
                                                             'bars': {'ligovskiy': {'hours': '14:00–02:00'}}}})
        assert sorted(saved['changed']) == ['bars.ligovskiy.hours', 'tone']
        assert saved['brief']['updated_by'] == 'owner · агент'

        created = rig.ok('content_material_create', {
            'title': 'Таплист пятницы', 'kind': 'live', 'live_source': 'taplist', 'planned_date': '2026-10-09',
            'base_text': 'Сегодня в {бар} на кранах {кранов}:\n{таплист}',
            'agent_rationale': 'Рубрика брифа «Таплист пятницы».', 'shot_list': 'Стена кранов.'})
        material = created['material']
        assert material['origin'] == 'agent' and material['agent_draft'] is True
        assert material['created_by'] == 'owner · агент' and material['month'] == '2026-10'
        added = rig.ok('content_placements_add', {'material_id': material['id'], 'channel': 'telegram',
                                                  'bars': ['bolshoy', 'ligovskiy'], 'time': '16:00'})
        assert len(added['created']) == 2
        assert all(p['date'] == '2026-10-09' for p in added['material']['placements'])

        post = rig.ok('content_material_create', {'title': 'Команда Лиговского', 'month': '2026-10',
                                                  'base_text': 'Знакомьтесь.', 'media_required': True,
                                                  'shot_list': 'Бармены у стойки, дневной свет.'})['material']
        rig.ok('content_placements_add', {'material_id': post['id'], 'channel': 'instagram',
                                          'date': '2026-10-20', 'time': '19:00'})

        preview = rig.ok('content_approve_preview', {'month': '2026-10', 'origin': 'agent'})
        ready = {item['placement_id'] for item in preview['will_approve']}
        assert set(added['created']) <= ready
        stays = {item['material_id']: [m['code'] for m in item['missing']] for item in preview['stays_draft']}
        assert stays.get(post['id']) == ['no_media']
        assert rig.ok('content_approve_preview', {'month': '2026-10', 'origin': 'human'})['will_approve'] == []

        repeat = rig.ok('content_material_repeat', {'material_id': material['id'], 'weekdays': [4]})
        assert len(repeat['created']) == 3                      # 16, 23, 30 октября
        month = rig.ok('content_plan_get', {'month': '2026-10'})
        assert month['stats']['materials'] == 5

        wrong = rig.call('content_placements_add', {'material_id': material['id'], 'channel': 'telegram',
                                                    'bar': 'bolshoy'})
        assert wrong.is_error and 'bar' in wrong.text_value      # схема, до маршрута

        gone = rig.ok('content_agent_drafts_delete', {'month': '2026-10'})
        assert len(gone['deleted']) == 5 and gone['skipped'] == []

        review = rig.ok('content_review_add', {'source': 'yandex', 'bar': 'bolshoy', 'rating': 5,
                                               'text': 'Отличный таплист и уютно.'})['review']
        waiting = rig.ok('content_reviews_list', {'all': True, 'status': 'new'})
        assert [r['id'] for r in waiting['reviews']] == [review['id']]
        drafted = rig.ok('content_review_update', {'review_id': review['id'], 'reply_draft': 'Спасибо! '})
        assert drafted['review']['reply_draft'] == 'Спасибо! ' and drafted['review']['status'] == 'new'
        linked = rig.ok('content_review_to_material', {'review_id': review['id'], 'month': '2026-10'})
        assert linked['month'] == '2026-10'
        again = rig.call('content_review_to_material', {'review_id': review['id']})
        assert again.is_error and again.http_status == 409
        attention = rig.ok('content_attention', {'bar': 'bolshoy'})
        assert attention['reviews_unanswered'] == 1 and attention['content_available'] is True


def test_bridge_publish_workflow():
    """Отправка через мост (поддельный Telegram): каналы выключены по умолчанию, настройка
    и проверка канала, «Отправить сейчас» до и после включения, тестовое сообщение,
    компактный месяц, учёт правок, аудитория и zip. Раскладка аргументов (тело, запрос, путь)."""
    if not _bridge_available():
        return
    with _BridgeRig() as rig:
        state = rig.ok('content_channels_get', {})
        assert state['channels']['enabled'] is False and state['token_source'] == 'taplist'
        assert state['delivery']['telegram']['bolshoy']['connected'] is False
        assert 'test-token' not in json_dumps(state)                              # токен не отдаётся

        bad = rig.call('content_channels_update', {'telegram': {'bolshoy': {'chat': 't.me/+secretinvite'}}})
        assert bad.is_error and bad.http_status == 400
        saved = rig.ok('content_channels_update', {'telegram': {'bolshoy': {'chat': 'https://t.me/kult_vo',
                                                                            'title': 'Культура ВО'}}})
        assert saved['channels']['telegram']['bolshoy']['chat'] == '@kult_vo'
        checked = rig.ok('content_channel_check', {'bar': 'bolshoy'})
        assert checked['check']['ok'] and checked['check']['can_post'] and checked['bot_username'] == 'kult_test_bot'
        assert [c[0] for c in rig.telegram.calls] == ['getMe', 'getChat', 'getChatMember']

        material = rig.ok('content_material_create', {'title': 'Анонс', 'month': '2026-10',
                                                      'base_text': 'Сегодня квиз в 20:00'})['material']
        pid = rig.ok('content_placements_add', {'material_id': material['id'], 'channel': 'telegram',
                                                'bars': ['bolshoy'], 'date': '2026-10-09',
                                                'time': '18:00'})['created'][0]
        rig.ok('content_approve', {'placement_ids': [pid]})
        off = rig.call('content_publish_now', {'placement_id': pid})
        assert off.is_error and off.http_status == 409 and 'выключена' in off.text_value
        rig.ok('content_channels_update', {'enabled': True})
        queued = rig.ok('content_publish_now', {'placement_id': pid})
        assert queued['queued'] is True and queued['placement']['status'] == 'approved'   # в очередь
        import core.content_publisher as pub
        report = pub.publish_due(transport=rig.telegram, guest_transport=rig.telegram, store=rig.plan,
                                 channels=rig.channels, sleep=lambda s: None, clock=lambda: 0.0)
        assert report['sent'] == 1                                          # отправил планировщик
        sent = rig.ok('content_material_get', {'material_id': material['id']})['material']['placements'][0]
        assert sent['status'] == 'published' and sent['post_url'].startswith('https://t.me/kult_vo/')
        assert rig.telegram.calls[-1][0] == 'sendMessage'
        assert rig.telegram.calls[-1][1] == {'chat_id': '@kult_vo', 'text': 'Сегодня квиз в 20:00',
                                             'disable_web_page_preview': False}
        test = rig.ok('content_channel_test', {'bar': 'bolshoy'})
        assert test['ok'] and test['message_id'] and rig.telegram.calls[-1][1]['text'] == 'Проверка связи с сайтом'

        compact = rig.ok('content_plan_get', {'month': '2026-10', 'compact': True})
        assert compact['compact'] is True and 'bars' not in compact
        item = compact['materials'][0]
        assert set(item) == {'id', 'title', 'kind', 'month', 'in_month', 'date', 'origin', 'agent_draft',
                             'summary', 'placements'}
        assert item['placements'][0] == {'id': pid, 'channel': 'telegram', 'bar': 'bolshoy', 'date': '2026-10-09',
                                         'time': '18:00', 'display_state': 'published'}
        full = rig.ok('content_plan_get', {'month': '2026-10'})
        assert 'delivery' in full and 'delivery_connected' in full and full['audiences'][0]['size'] == 7

        edits = rig.ok('content_agent_edits', {'months': 1})
        assert edits['counts']['agent_materials'] == 1 and edits['items'] == []     # правок людей не было
        audience = rig.ok('content_audience', {'segment': 'bot_bar', 'bar': 'ligovskiy'})
        assert (audience['size'], audience['bar'], audience['subscribers_total']) == (7, 'ligovskiy', 7)
        archive = rig.call('content_material_download', {'material_id': material['id']})
        assert not archive.is_error
        assert any(b.get('type') == 'resource' and b['resource']['mimeType'] == 'application/zip'
                   for b in archive.content)
        missing = rig.call('content_material_download', {'material_id': 'm_000000000000'})
        assert missing.is_error and missing.http_status == 404


def json_dumps(value):
    import json
    return json.dumps(value, ensure_ascii=False)


# --------------------------------------------------------------------------- тесты: совместимость

def test_python310_fstrings():
    """CI гоняет 3.10: внутри f-строки нельзя повторять её кавычку, ставить \\ и комментарий."""
    path = os.path.join(REPO, 'core', 'mcp', 'tools', 'content.py')
    src = open(path, encoding='utf-8').read()
    start = getattr(tokenize, 'FSTRING_START', None)
    if start is None:        # Python < 3.12: такой код просто не разобрался бы при импорте
        return
    stack = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == start:
            quote = tok.string[len(tok.string.rstrip('\'"')):]
            assert not (stack and quote[0] in stack[-1]), 'строка ' + str(tok.start[0])
            stack.append(quote)
        elif tok.type == tokenize.FSTRING_END:
            stack.pop()
        elif stack and tok.type == tokenize.STRING:
            body = tok.string.lstrip('rRbBuU')
            assert body[0] not in stack[-1] and '\\' not in tok.string, 'строка ' + str(tok.start[0])
        elif stack:
            assert tok.type != tokenize.COMMENT, 'строка ' + str(tok.start[0])


# --------------------------------------------------------------------------- самозапуск

if __name__ == '__main__':
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print('ok   ', name)
        except Exception as e:  # noqa: BLE001 — отчёт по каждому тесту
            failed += 1
            print('FAIL ', name, '-', repr(e)[:600])
    print('\n' + str(len(tests) - failed) + ' passed, ' + str(failed) + ' failed')
    sys.exit(1 if failed else 0)

"""MCP-коннекторы сервиса и страница «Доступ агентов».

Коннекторы (публичные для гейта авторизации: у ИИ-клиента нет cookie сайта;
токен проверяет сам протокол — core/mcp/auth.py):
    POST /mcp                     все разделы (endpoint mcp.mcp_all)
    POST /mcp/<домен>             content | stocks | analytics | staff (mcp.mcp_domain)
    POST /mcp/<режим>             все разделы в режиме read | draft (mcp.mcp_domain)
    POST /mcp/<домен>/<режим>     раздел в режиме read | draft (mcp.mcp_domain)
    Сегмент после /mcp/ — домен, если он в spec.DOMAINS, иначе режим read или draft,
    иначе 404. Без суффикса режима — full; суффикса /full нет (404): у каждой пары
    (домен, режим) ровно один адрес, к нему OAuth привязывает токен. Действует более
    строгий из режима адреса и режима токена (core/mcp/protocol.py).
    GET/DELETE на тех же путях -> 405 (SSE-потока и сессий нет), см. core/mcp/protocol.py.

Страница и админ-API (только администратор, @admin_required):
    GET    /admin/mcp                          страница (templates/admin_mcp.html)
    GET    /api/admin/mcp/tokens               {tokens, domains}
    POST   /api/admin/mcp/tokens               {name, domains: [...] | ["*"], expires_days?, mode?}
                                               -> {token, row, commands}; токен показывается ОДИН раз
    DELETE /api/admin/mcp/tokens/<id>          отозвать -> {ok}
    GET    /api/admin/mcp/grants               {available, grants} — подключённые OAuth-приложения
    DELETE /api/admin/mcp/grants/<client_id>   погасить все токены клиента -> {ok}
    GET    /api/admin/mcp/audit                ?limit=&tool=&status= -> {items}
    GET    /api/admin/mcp/settings             {settings, subscribers, bot_configured, defaults}
    PUT    /api/admin/mcp/settings             {notify_chat_id?, oauth_redirect_hosts?} -> то же
Админ-API в охват MCP не входит (core/mcp/tools/common.py, EXCLUDED): агент не
управляет доступом к себе — выпуск токенов, отзыв и настройки только руками владельца.
"""
import os

from flask import Blueprint, jsonify, render_template, request

from core.auth_guard import admin_required, current_user
from core.mcp import audit, protocol, registry, settings, tokens
from core.mcp.principal import ALL_DOMAINS
from core.mcp.spec import DOMAINS, MODE_TITLES, MODES

mcp_bp = Blueprint('mcp', __name__)


# ------------------------------------------------------------------ коннекторы

MCP_METHODS = ['POST', 'GET', 'DELETE']


@mcp_bp.route('/mcp', methods=MCP_METHODS, strict_slashes=False)
def mcp_all():
    return protocol.handle_http(request, None)


@mcp_bp.route('/mcp/<domain>', methods=MCP_METHODS, strict_slashes=False)
@mcp_bp.route('/mcp/<domain>/<mode>', methods=MCP_METHODS, strict_slashes=False)
@mcp_bp.route('/mcp/<domain>/<mode>/<path:rest>', methods=MCP_METHODS)
def mcp_domain(domain, mode=None, rest=None):
    """/mcp/<домен>, /mcp/<режим> и /mcp/<домен>/<режим> (разбор — в докстринге модуля).

    Более глубокий путь под /mcp — сразу 404 JSON: иначе он ушёл бы в общий гейт сайта
    и ИИ-клиент получил бы перенаправление на страницу входа вместо понятного ответа.
    """
    if rest is not None:
        return protocol.not_found('Такого адреса MCP нет: коннектор — /mcp[/<раздел>][/read|/draft].')
    if domain not in DOMAINS and mode is None and domain in protocol.URL_MODES:
        return protocol.handle_http(request, None, domain)
    return protocol.handle_http(request, domain, mode)


# ------------------------------------------------------------------ помощники

def _base() -> str:
    return request.host_url.rstrip('/')


def _error(message: str, status: int = 400):
    return jsonify({'error': message}), status


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _login() -> str:
    user = current_user() or {}
    return user.get('login') or ''


def connect_commands(base: str, raw_token: str, domains, mode: str = 'full') -> list:
    """Готовые команды `claude mcp add` для выпущенного токена.

    Адреса — с суффиксом режима токена (/read, /draft; для full — без суффикса), имя
    сервера в Claude Code — тоже с режимом (kultura-content-draft), чтобы подключения
    разных режимов не путались. Полный коннектор /mcp доступен только токену на все
    разделы ('*'), поэтому его команда — только для такого токена.
    """
    suffix = '' if mode == 'full' else '/' + mode
    tag = '' if mode == 'full' else '-' + mode
    picked = list(DOMAINS) if ALL_DOMAINS in domains else [d for d in DOMAINS if d in domains]
    header = f'--header "Authorization: Bearer {raw_token}"'
    title_suffix = '' if mode == 'full' else f' ({MODE_TITLES[mode].lower()})'
    out = []
    for key in picked:
        path = DOMAINS[key].connector_path + suffix
        out.append({'connector': path, 'title': DOMAINS[key].title + title_suffix,
                    'command': f'claude mcp add --transport http kultura-{key}{tag} {base}{path} {header}'})
    if ALL_DOMAINS in domains:
        path = '/mcp' + suffix
        out.append({'connector': path, 'title': 'Все разделы' + title_suffix,
                    'command': f'claude mcp add --transport http kultura{tag} {base}{path} {header}'})
    return out


def _oauth_module():
    try:
        from core.mcp import oauth
    except ImportError:
        return None
    return oauth


def _subscribers() -> list:
    try:
        from core.open_check_subscribers import get_recipients
        return list(get_recipients())
    except Exception:  # noqa: BLE001 — страница открывается и без файла подписчиков
        return []


def _settings_payload() -> dict:
    return {'settings': settings.all_settings(),
            'defaults': settings.DEFAULTS,
            'subscribers': _subscribers(),
            'bot_configured': bool(os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN'))}


# ------------------------------------------------------------------ страница

@mcp_bp.route('/admin/mcp', methods=['GET'])
@admin_required
def admin_mcp_page():
    base = _base()
    connectors = []
    for row in registry.summary():
        connectors.append(dict(row, url=base + row['path']))
    return render_template('admin_mcp.html', connectors=connectors, domains=DOMAINS, modes=MODES,
                           mode_titles=MODE_TITLES,
                           load_errors=registry.load_errors(), base_url=base,
                           oauth_available=_oauth_module() is not None,
                           audit_statuses=audit.STATUSES, tool_names=sorted(t.name for t in registry.all_tools()))


# ------------------------------------------------------------------ токены

@mcp_bp.route('/api/admin/mcp/tokens', methods=['GET'])
@admin_required
def admin_tokens_list():
    return jsonify({'tokens': tokens.list_tokens(),
                    'domains': [{'key': k, 'title': d.title, 'path': d.connector_path} for k, d in DOMAINS.items()],
                    'modes': [{'key': m, 'title': MODE_TITLES[m]} for m in MODES]})


@mcp_bp.route('/api/admin/mcp/tokens', methods=['POST'])
@admin_required
def admin_tokens_create():
    body = _json_body()
    try:
        raw, row = tokens.create(current_user(), body.get('name'), body.get('domains'), body.get('expires_days'),
                                 mode=body.get('mode') or 'full')
    except ValueError as exc:
        return _error(str(exc))
    return jsonify({'token': raw, 'row': row,
                    'commands': connect_commands(_base(), raw, row['domains'], row['mode'])})


@mcp_bp.route('/api/admin/mcp/tokens/<token_id>', methods=['DELETE'])
@admin_required
def admin_tokens_revoke(token_id):
    if tokens.get(token_id) is None:
        return _error('Нет такого токена', 404)
    changed = tokens.revoke(token_id, by=_login())
    return jsonify({'ok': True, 'revoked': changed})


# ------------------------------------------------------------------ OAuth-приложения

@mcp_bp.route('/api/admin/mcp/grants', methods=['GET'])
@admin_required
def admin_grants_list():
    oauth = _oauth_module()
    if oauth is None or not hasattr(oauth, 'list_grants'):
        return jsonify({'available': False, 'grants': []})
    return jsonify({'available': True, 'grants': oauth.list_grants()})


@mcp_bp.route('/api/admin/mcp/grants/<client_id>', methods=['DELETE'])
@admin_required
def admin_grants_revoke(client_id):
    oauth = _oauth_module()
    if oauth is None or not hasattr(oauth, 'revoke_client'):
        return _error('OAuth не подключён', 404)
    result = oauth.revoke_client(client_id)
    if isinstance(result, dict) and result.get('found') is False:
        return _error('Нет такого приложения', 404)
    return jsonify({'ok': True, 'result': result})


# ------------------------------------------------------------------ журнал

@mcp_bp.route('/api/admin/mcp/audit', methods=['GET'])
@admin_required
def admin_audit():
    status = (request.args.get('status') or '').strip() or None
    tool = (request.args.get('tool') or '').strip() or None
    try:
        items = audit.recent(limit=request.args.get('limit', 100), tool=tool, status=status)
    except ValueError as exc:
        return _error(str(exc))
    return jsonify({'items': items})


# ------------------------------------------------------------------ настройки

@mcp_bp.route('/api/admin/mcp/settings', methods=['GET'])
@admin_required
def admin_settings_get():
    return jsonify(_settings_payload())


@mcp_bp.route('/api/admin/mcp/settings', methods=['PUT'])
@admin_required
def admin_settings_put():
    body = _json_body()
    known = [k for k in body if k in settings.DEFAULTS]
    unknown = [k for k in body if k not in settings.DEFAULTS]
    if unknown:
        return _error('Неизвестные настройки: ' + ', '.join(sorted(unknown)))
    if not known:
        return _error('Нечего сохранять')
    try:
        # Сначала проверяются все поля, потом пишутся: ошибка во втором поле не
        # должна оставить первое сохранённым наполовину.
        cleaned = {key: settings.KNOWN[key](body[key]) if key in settings.KNOWN else body[key] for key in known}
    except ValueError as exc:
        return _error(str(exc))
    for key, value in cleaned.items():
        settings.set(key, value, by=_login())
    return jsonify(_settings_payload())

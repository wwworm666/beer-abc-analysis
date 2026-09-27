"""Маршруты OAuth 2.1 для MCP-коннекторов: метаданные, регистрация, согласие, токены, отзыв.

Логика и правила — core/mcp/oauth.py (там же подробный docstring). Здесь только HTTP:
разбор запроса, ответы по RFC и страница согласия templates/mcp_consent.html.

Маршруты (имена функций зафиксированы контрактом — их вносит в
core/auth_guard.PUBLIC_ENDPOINTS агент ядра; authorize НЕ публичный):

    GET  /.well-known/oauth-protected-resource[/<путь коннектора>]  protected_resource_metadata
    GET  /.well-known/oauth-authorization-server                     authorization_server_metadata
    POST /oauth/register                                              register_client
    GET/POST /oauth/authorize                                         authorize
    POST /oauth/token                                                 token
    POST /oauth/revoke                                                revoke

Безопасность страницы согласия:
- вход на сайт обязателен (глобальный гейт отправляет анонима на /login?next=…); согласие
  даёт только активный администратор, остальным — 403 со страницей-пояснением;
- POST формы проверяет CSRF-токен из сессии (session['mcp_oauth_csrf']) и заново проверяет
  все параметры запроса — решение принимается ровно по тому, что проверено;
- режим доступа гранта выбирает владелец (радиокнопки): равный режиму адреса коннектора
  или строже; подделанное значение мягче адреса -> страница ошибки, код не выдаётся;
- ответ после POST — 303 (браузер повторит его как GET; 307 переслал бы форму на
  claude.ai, а колбэк Claude принимает только GET);
- X-Frame-Options: DENY и CSP frame-ancestors 'none' — страницу нельзя встроить во фрейм
  и «прокликать» (clickjacking); Referrer-Policy: no-referrer; Cache-Control: no-store.
  CSP без form-action: Chrome применяет его и к редиректу после отправки формы, а редирект
  уходит на хост клиента (claude.ai).

CORS (Access-Control-Allow-Origin: *) — только на метаданных, регистрации, token и revoke:
браузерные MCP-клиенты (MCP Inspector) ходят туда из JS. Cookie там не используются, так
что открытый CORS ничего не даёт чужой странице. На /oauth/authorize CORS нет.
"""
import json
import secrets
from urllib.parse import parse_qsl, quote

from flask import Blueprint, jsonify, make_response, redirect, render_template, request, session, url_for

from core import auth_guard
from core.mcp import oauth

mcp_oauth_bp = Blueprint('mcp_oauth', __name__)

CSRF_SESSION_KEY = 'mcp_oauth_csrf'
_CORS_ENDPOINTS = frozenset({'protected_resource_metadata', 'authorization_server_metadata',
                             'register_client', 'token', 'revoke'})
_FORM_CONTROL_FIELDS = ('csrf_token', 'decision', 'mode')   # поля формы, не параметры OAuth


# ------------------------------------------------------------------ общие помощники


def _base() -> str:
    """База сайта из request.host_url (за Caddy + ProxyFix — внешний https-адрес)."""
    return oauth.base_url(request.host_url)


def _endpoints(base: str) -> dict:
    return {
        'authorization_endpoint': base + url_for('mcp_oauth.authorize'),
        'token_endpoint': base + url_for('mcp_oauth.token'),
        'registration_endpoint': base + url_for('mcp_oauth.register_client'),
        'revocation_endpoint': base + url_for('mcp_oauth.revoke'),
    }


def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Pragma'] = 'no-cache'
    return resp


def _oauth_error_response(err: 'oauth.OAuthError'):
    resp = jsonify(err.body())
    resp.status_code = err.status
    if err.www_authenticate:
        resp.headers['WWW-Authenticate'] = err.www_authenticate
    if err.status == 429:
        resp.headers['Retry-After'] = '600'
    return _no_store(resp)


def _request_params():
    """Параметры тела token/revoke как [(имя, [значения])].

    Форма x-www-form-urlencoded (RFC 6749 §3.2); JSON-объект тоже принимается (некоторые
    клиенты так шлют) — берутся его строковые поля. Query string намеренно не читается.
    Тело читается сами, не больше oauth.MAX_FORM_BYTES: эндпоинты публичные, а разбор формы
    werkzeug у chunked-запроса без Content-Length не ограничен (в Flask 3.0 нет лимита на
    запрос). Если форму уже разобрал кто-то раньше (поток пуст) — берём разобранную.
    """
    limit = oauth.MAX_FORM_BYTES
    too_large = oauth.OAuthError('invalid_request', 'request body is too large', status=413)
    if request.content_length is not None and request.content_length > limit:
        raise too_large
    raw = request.stream.read(limit + 1)
    if len(raw) > limit:
        raise too_large
    if not raw:
        return list(request.form.lists()) if request.form else []
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise oauth.OAuthError('invalid_request', 'request body must be UTF-8')
    if request.mimetype == 'application/json':
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            raise oauth.OAuthError('invalid_request', 'malformed JSON body')
        if not isinstance(data, dict):
            raise oauth.OAuthError('invalid_request', 'JSON body must be an object')
        return [(k, [v]) for k, v in data.items() if isinstance(v, str)]
    try:
        pairs = parse_qsl(text, keep_blank_values=True, max_num_fields=oauth.MAX_FORM_FIELDS)
    except ValueError:
        raise oauth.OAuthError('invalid_request', 'too many request parameters')
    grouped = {}
    for key, value in pairs:
        grouped.setdefault(key, []).append(value)
    return list(grouped.items())


@mcp_oauth_bp.after_request
def _security_headers(resp):
    endpoint = (request.endpoint or '').rsplit('.', 1)[-1]
    if endpoint in _CORS_ENDPOINTS:
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = ('Authorization, Content-Type, '
                                                        'MCP-Protocol-Version')
        resp.headers['Access-Control-Max-Age'] = '600'
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    return resp


# ------------------------------------------------------------------ метаданные


@mcp_oauth_bp.route('/.well-known/oauth-protected-resource', methods=['GET'],
                    defaults={'subpath': ''})
@mcp_oauth_bp.route('/.well-known/oauth-protected-resource/<path:subpath>', methods=['GET'])
def protected_resource_metadata(subpath):
    """RFC 9728: корень и 'mcp' — полный коннектор, 'mcp/<домен>' — коннектор домена."""
    doc = oauth.protected_resource_metadata(_base(), subpath)
    if doc is None:
        resp = jsonify({'error': 'not_found',
                        'error_description': 'no MCP connector at this path'})
        resp.status_code = 404
        return resp
    resp = jsonify(doc)
    resp.headers['Cache-Control'] = 'public, max-age=300'
    return resp


@mcp_oauth_bp.route('/.well-known/oauth-authorization-server', methods=['GET'])
def authorization_server_metadata():
    """RFC 8414. /.well-known/openid-configuration сознательно не отдаём: мы не OpenID-провайдер
    (нет id_token и jwks), а MCP-клиенты сначала спрашивают этот адрес."""
    base = _base()
    resp = jsonify(oauth.authorization_server_metadata(base, _endpoints(base)))
    resp.headers['Cache-Control'] = 'public, max-age=300'
    return resp


# ------------------------------------------------------------------ регистрация (RFC 7591)


@mcp_oauth_bp.route('/oauth/register', methods=['POST'])
def register_client():
    ip = request.remote_addr or ''
    if not oauth.registration_allowed(ip):
        return _oauth_error_response(oauth.OAuthError(
            'temporarily_unavailable', 'too many client registrations from this address, '
            'retry later', status=429))
    limit = oauth.MAX_REGISTRATION_BYTES
    if request.content_length is not None and request.content_length > limit:
        return _oauth_error_response(oauth.OAuthError(
            'invalid_client_metadata', 'registration request is too large', status=413))
    # Читаем не больше limit+1 байт (у chunked-запросов Content-Length нет).
    raw = request.stream.read(limit + 1)
    if len(raw) > limit:
        return _oauth_error_response(oauth.OAuthError(
            'invalid_client_metadata', 'registration request is too large', status=413))
    try:
        body = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError, RecursionError):   # RecursionError: '[[[[…' в 16 КБ
        return _oauth_error_response(oauth.OAuthError(
            'invalid_client_metadata', 'registration body must be a JSON object'))
    try:
        result = oauth.register_client(body, ip)
    except oauth.OAuthError as e:
        return _oauth_error_response(e)
    resp = jsonify(result)
    resp.status_code = 201
    return _no_store(resp)


# ------------------------------------------------------------------ согласие (/oauth/authorize)


def _csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _csrf_ok(submitted) -> bool:
    expected = session.get(CSRF_SESSION_KEY)
    # Сравниваем байты: compare_digest на str с не-ASCII бросает TypeError (был бы 500).
    return (isinstance(expected, str) and isinstance(submitted, str) and len(expected) >= 32
            and secrets.compare_digest(expected.encode('utf-8'), submitted.encode('utf-8')))


def _page(mode: str, status: int, **ctx):
    """Страница согласия/ошибки с защитными заголовками. mode: consent | error | forbidden."""
    nonce = secrets.token_urlsafe(16)
    html = render_template('mcp_consent.html', mode=mode, csp_nonce=nonce, **ctx)
    resp = make_response(html, status)
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'nonce-%s'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'" % nonce)
    resp.headers['Referrer-Policy'] = 'no-referrer'
    return _no_store(resp)


def _error_page(message: str, status: int = 400, title: str = 'Подключение не удалось'):
    return _page('error', status, error_title=title, error_message=message)


def _login_redirect():
    nxt = request.full_path if request.query_string else request.path
    try:
        login_url = url_for('auth.login', next=nxt)
    except Exception:  # noqa: BLE001 — стенд без auth-blueprint
        login_url = '/login?next=' + quote(nxt, safe='')
    return redirect(login_url)


def _consent_context(req: 'oauth.AuthorizationRequest', user: dict) -> dict:
    client = req.client
    connector = oauth.describe_connector(req.resource)
    host = oauth.redirect_host(req.redirect_uri)
    return {
        'client_name': client['client_name'],
        'client_id': client['client_id'],
        'client_registered_at': oauth.format_msk(client['created_at']),
        'redirect_uri': req.redirect_uri,
        'redirect_host': host,
        'is_loopback': oauth.is_loopback_redirect(req.redirect_uri),
        'is_claude_host': host in oauth.PINNED_CALLBACK_PATHS,
        'connector': connector,
        'user_display': user.get('display_name') or user.get('login'),
        'user_login': user.get('login'),
        'echo': list(req.echo),
        'csrf_token': _csrf_token(),
        'access_hours': oauth.ACCESS_TOKEN_TTL // 3600,
        'refresh_days': oauth.REFRESH_TOKEN_TTL // 86400,
        # Режим: адрес коннектора задаёт потолок, владелец может выбрать строже.
        'url_mode': req.url_mode,
        'url_mode_title': oauth.MODE_TITLES[req.url_mode],
        'mode_options': [{'key': m, 'title': oauth.MODE_TITLES[m],
                          'desc': oauth.MODE_DESCRIPTIONS[m], 'checked': m == req.url_mode}
                         for m in oauth.allowed_modes(req.url_mode)],
    }


@mcp_oauth_bp.route('/oauth/authorize', methods=['GET', 'POST'])
def authorize():
    """GET — проверить запрос и показать согласие; POST — решение владельца («Разрешить»/«Отказать»)."""
    user = auth_guard.current_user()
    if not user:
        return _login_redirect()
    if not (user.get('is_admin') and user.get('active', True)):
        return _page('forbidden', 403, user_login=user.get('login'))

    base = _base()
    issuer = oauth.issuer_for(base)
    is_post = request.method == 'POST'
    if is_post:
        if not _csrf_ok(request.form.get('csrf_token')):
            return _error_page('Форма согласия устарела или отправлена не со страницы этого '
                               'сайта, поэтому решение не принято.')
        params = {k: v for k, v in request.form.lists() if k not in _FORM_CONTROL_FIELDS}
    else:
        params = {k: v for k, v in request.args.lists()}

    try:
        req = oauth.validate_authorization_request(params, base)
    except oauth.AuthorizeError as e:
        if e.redirect_uri is None:
            return _error_page(e.message_ru)
        resp = redirect(oauth.authorization_error_redirect(e, issuer), code=303 if is_post else 302)
        return _no_store(resp)

    if not is_post:
        return _page('consent', 200, **_consent_context(req, user))

    decision = request.form.get('decision')
    if decision == 'allow':
        try:
            mode = oauth.choose_mode(req.url_mode, request.form.get('mode'))
        except ValueError:
            return _error_page('Выбран недопустимый режим доступа: можно оставить режим адреса '
                               'коннектора или выбрать более строгий.')
        code = oauth.issue_code(req, user['id'], mode)
        target = oauth.success_redirect(req, code, issuer)
    elif decision == 'deny':
        target = oauth.denied_redirect(req, issuer)
    else:
        return _error_page('Не выбрано решение: ни «Разрешить», ни «Отказать».')
    return _no_store(redirect(target, code=303))


# ------------------------------------------------------------------ токены и отзыв


@mcp_oauth_bp.route('/oauth/token', methods=['POST'])
def token():
    """RFC 6749 §3.2: authorization_code (с PKCE) и refresh_token (с ротацией)."""
    try:
        params = oauth.single_params(_request_params())
        client = oauth.authenticate_client(request.headers.get('Authorization'), params)
        grant_type = params.get('grant_type')
        if grant_type == 'authorization_code':
            body = oauth.exchange_authorization_code(client, params)
        elif grant_type == 'refresh_token':
            body = oauth.refresh_tokens(client, params)
        elif not grant_type:
            raise oauth.OAuthError('invalid_request', 'grant_type is required')
        else:
            raise oauth.OAuthError('unsupported_grant_type',
                                   'only authorization_code and refresh_token are supported')
    except oauth.OAuthError as e:
        return _oauth_error_response(e)
    return _no_store(jsonify(body))


@mcp_oauth_bp.route('/oauth/revoke', methods=['POST'])
def revoke():
    """RFC 7009: 200 и для отозванного, и для неизвестного токена. Клиент, если представился,
    аутентифицируется (неверный секрет -> 401); не представился — отзыв по владению токеном."""
    try:
        params = oauth.single_params(_request_params())
        raw = params.get('token')
        if not raw:
            raise oauth.OAuthError('invalid_request', 'token is required')
        client = None
        if oauth._parse_basic(request.headers.get('Authorization')) is not None \
                or params.get('client_id'):
            client = oauth.authenticate_client(request.headers.get('Authorization'), params)
        oauth.revoke_token(raw, client)
    except oauth.OAuthError as e:
        return _oauth_error_response(e)
    return _no_store(make_response('', 200))

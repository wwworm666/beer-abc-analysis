"""
Гейт авторизации: подключается к Flask-приложению одним вызовом init_auth(app).

Модель: личный аккаунт на каждого, вход по логину+паролю. После входа все
бизнес-страницы доступны всем (равные права); отдельным флагом is_admin
ограничена только страница управления аккаунтами.

«Вход один раз»: сессия в подписанном cookie (config.SECRET_KEY стабилен),
permanent + скользящее продление, срок 180 дней.

CSRF: отдельных токенов нет; защита — SESSION_COOKIE_SAMESITE='Lax', при которой
браузер не шлёт cookie на кросс-сайтовые POST/PUT/DELETE (этого достаточно для
внутреннего инструмента). См. docs/auth.md, раздел про безопасность.
"""

import os
from datetime import timedelta
from functools import wraps

from flask import session, request, redirect, url_for, jsonify, g
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from core.auth_manager import get_auth_manager


SESSION_DAYS = 180

# Эндпоинты, доступные без входа. Используем имена эндпоинтов (а не пути) — надёжнее.
PUBLIC_ENDPOINTS = {
    'auth.login',
    'auth.logout',
    'auth.setup',
    'static',                          # /static/* (CSS/JS/иконки/манифест)
    'serve_manifest',                  # app.py: /static/manifest.json
    'misc.telegram_webhook_handler',   # Telegram POST'ит сюда без cookie
}


def init_auth(app):
    """Сконфигурировать сессии и повесить глобальный гейт на приложение."""
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=SESSION_DAYS)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = _cookie_secure()
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # скользящее продление срока

    # Caddy терминирует TLS и проксирует по http на localhost. Доверяем заголовкам
    # X-Forwarded-* ровно от одного прокси, чтобы request.is_secure / url_for(_external)
    # были корректны (один Caddy перед приложением).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.before_request(_auth_gate)
    app.context_processor(_inject_current_user)


def _cookie_secure() -> bool:
    """Secure-флаг cookie. На проде за Caddy всегда HTTPS -> True; локально по http
    Secure-cookie не отправится, поэтому там False. Признак прода — тот же, что для
    путей БД (/kultura). Переопределяется env SESSION_COOKIE_SECURE."""
    val = os.getenv('SESSION_COOKIE_SECURE')
    if val is not None:
        return val.strip().lower() in ('1', 'true', 'yes', 'on')
    return os.path.isdir('/kultura')


def _load_user():
    """Текущий пользователь по сессии (с кэшем в g на время запроса)."""
    cached = getattr(g, '_current_user', 'unset')
    if cached != 'unset':
        return cached
    user = None
    uid = session.get('user_id')
    if uid:
        user = get_auth_manager().get_by_id(uid)
        if user is None or not user.get('active'):
            # Аккаунт удалён/выключен после входа — рвём сессию.
            session.clear()
            user = None
    g._current_user = user
    return user


def current_user():
    """Публичный аксессор: словарь юзера или None."""
    return _load_user()


def login_user(user: dict):
    """Записать вход в сессию (вызывается из /login после проверки пароля)."""
    session.clear()
    session['user_id'] = user['id']
    session.permanent = True
    g._current_user = user


def logout_user():
    session.clear()
    g._current_user = None


def _wants_json() -> bool:
    p = request.path
    return p.startswith('/api/') or '/api/' in p or request.accept_mimetypes.best == 'application/json'


def _auth_gate():
    """Глобальный before_request: всё закрыто, кроме PUBLIC_ENDPOINTS."""
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if _load_user():
        return None
    # Не авторизован.
    if _wants_json():
        return jsonify({'error': 'Требуется вход', 'auth_required': True}), 401
    nxt = request.full_path if request.query_string else request.path
    return redirect(url_for('auth.login', next=nxt))


def _inject_current_user():
    return {'current_user': _load_user()}


def admin_required(f):
    """Декоратор для маршрутов управления аккаунтами (только is_admin)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = _load_user()
        if not user:
            if _wants_json():
                return jsonify({'error': 'Требуется вход', 'auth_required': True}), 401
            return redirect(url_for('auth.login', next=request.path))
        if not user.get('is_admin'):
            if _wants_json():
                return jsonify({'error': 'Доступ только для администратора'}), 403
            return 'Доступ только для администратора', 403
        return f(*args, **kwargs)
    return wrapper

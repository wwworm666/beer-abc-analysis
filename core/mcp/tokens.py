"""Статические токены доступа для Claude Code (и любых клиентов с ручным заголовком).

Как пользоваться: владелец выпускает токен на странице «Доступ агентов» (/admin/mcp),
страница один раз показывает его вместе с готовой командой
    claude mcp add --transport http kultura-<домен> <сайт>/mcp/<домен>[/<режим>] \\
        --header "Authorization: Bearer <токен>"
Приложение Claude и расписания ходят через OAuth (core/mcp/oauth.py) — там токены
выдаются сами, этот модуль им не нужен.

Формат: 'kmcp_' + 40 символов secrets.token_urlsafe(30) (240 бит случайности).
Префикс kmcp_ отличает статический токен от OAuth (kmcpo_/kmcpr_) и позволяет
искать утёкшие токены в логах и переписке по шаблону.

Хранение: только sha256 от токена (сам токен не восстановить — потерянный
выпускается заново). В списке видны первые PREFIX_CHARS символов — чтобы
узнать токен в конфиге клиента.

Правила действия (verify_static):
- токен есть, не отозван, срок не истёк (срок необязателен: expires_days=None — бессрочный);
- last_used_at обновляется не чаще раза в LAST_USED_EVERY_S секунд — иначе каждый
  вызов агента писал бы в БД;
- права владельца (активный администратор) и домен коннектора проверяет
  core/mcp/auth.py на КАЖДОМ запросе: пока владелец выключен или не администратор,
  его токены не действуют. При удалении, отключении и снятии флага администратора
  routes/auth.py ещё и отзывает их (revoke_all_for_user) — возврат флага не оживляет
  старые токены.

Домены токена: список ключей spec.DOMAINS или ['*'] — все домены и полный коннектор /mcp.

Режим токена (spec.MODES): read — только чтение, draft — чтение и черновики, full —
всё. Действует более строгий из режима токена и режима адреса коннектора
(/mcp/<домен>/read и т. п.) — protocol.py. Таблицы, созданные до режимов, получают
колонку mode со значением 'full' (так эти токены и работали).

Статус в списке (list_tokens) учитывает и владельца: действующий токен выключенного,
удалённого или лишённого админства владельца показывается «владелец отключён» /
«не администратор» — он не работает, хотя сам не отозван.
"""
import hashlib
import json
import secrets
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core import msk_time
from core.mcp import db
from core.mcp.principal import ALL_DOMAINS, Principal
from core.mcp.spec import DOMAINS, MODES

TOKEN_PREFIX = 'kmcp_'
TOKEN_RANDOM_BYTES = 30        # token_urlsafe(30) = 40 символов base64url
PREFIX_CHARS = 12              # сколько первых символов показывать в списке ('kmcp_' + 7)
LAST_USED_EVERY_S = 60         # не чаще раза в минуту обновлять «последнее использование»
NAME_MAX = 80                  # имя токена — короткая подпись («ноутбук», «Claude Code офис»)
MAX_EXPIRES_DAYS = 3650        # срок больше 10 лет — это «бессрочный», его и выбирают

# Модуль экспортирует функцию list() (имя из контракта), поэтому встроенный список
# сохранён под своим именем до её объявления.
_builtin_list = list

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS static_tokens (
        id           TEXT PRIMARY KEY,           -- 'st_' + 16 hex
        token_hash   TEXT NOT NULL UNIQUE,       -- sha256(token) hex
        prefix       TEXT NOT NULL,              -- первые PREFIX_CHARS символов токена
        name         TEXT NOT NULL,
        domains      TEXT NOT NULL,              -- JSON-список, ["*"] — все
        user_id      INTEGER NOT NULL,
        user_login   TEXT NOT NULL,
        created_at   TEXT NOT NULL,              -- МСК ISO
        created_by   TEXT NOT NULL,
        last_used_at TEXT,
        expires_at   TEXT,                       -- NULL — бессрочный
        revoked_at   TEXT,
        revoked_by   TEXT,
        mode         TEXT NOT NULL DEFAULT 'full' -- read | draft | full (spec.MODES)
    )''',
    'CREATE INDEX IF NOT EXISTS idx_static_tokens_user ON static_tokens(user_id)',
)

_migrated = set()                 # пути БД, где проверена колонка mode (один раз на процесс)
_migrate_lock = threading.Lock()


def _ensure() -> None:
    """Схема + миграция: колонка mode для таблиц, созданных до режимов доступа.

    Проверка и ALTER — в одной транзакции BEGIN IMMEDIATE: второй gunicorn-воркер
    ждёт лок и видит уже добавленную колонку (ALTER дважды упал бы).
    """
    db.ensure_schema('static_tokens', SCHEMA)
    path = db.db_path()
    if path in _migrated:
        return
    with _migrate_lock:
        if path in _migrated:
            return
        with db.write() as conn:
            cols = {r['name'] for r in conn.execute('PRAGMA table_info(static_tokens)').fetchall()}
            if 'mode' not in cols:
                conn.execute("ALTER TABLE static_tokens ADD COLUMN mode TEXT NOT NULL DEFAULT 'full'")
        _migrated.add(path)


def _now() -> datetime:
    return msk_time.now().replace(microsecond=0)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def normalize_domains(domains: Any) -> List[str]:
    """Проверить и привести домены: ['*'] или непустое подмножество spec.DOMAINS в их порядке."""
    if domains is None or domains == ALL_DOMAINS:
        return [ALL_DOMAINS]
    if isinstance(domains, str):
        domains = [d for d in domains.replace(',', ' ').split() if d]
    if not isinstance(domains, (_builtin_list, tuple)):
        raise ValueError('Разделы токена — список, например ["content", "stocks"] или ["*"]')
    picked = [str(d).strip() for d in domains if str(d).strip()]
    if ALL_DOMAINS in picked:
        return [ALL_DOMAINS]
    unknown = [d for d in picked if d not in DOMAINS]
    if unknown:
        raise ValueError(f'Неизвестные разделы: {", ".join(unknown)}. Допустимые: {", ".join(DOMAINS)} или *')
    if not picked:
        raise ValueError('Выберите хотя бы один раздел или «все»')
    # Все четыре раздела по отдельности — это НЕ «*»: звёздочка даёт ещё и полный
    # коннектор /mcp и будущие разделы, поэтому выбирается только явно.
    return [d for d in DOMAINS if d in picked]


def _row_public(row) -> Dict[str, Any]:
    """Строка БД -> словарь для списка (без хэша) + вычисленный статус самого токена."""
    data = dict(row)
    data.pop('token_hash', None)
    data['domains'] = json.loads(data['domains'] or '[]')
    data['mode'] = data.get('mode') or 'full'
    data['status'] = _status(data)
    return data


def normalize_mode(mode: Any) -> str:
    """Режим токена: read | draft | full (пусто — full). Иначе ValueError."""
    value = str(mode or 'full').strip().lower()
    if value not in MODES:
        raise ValueError(f'Режим токена — один из: {", ".join(MODES)}')
    return value


def _owner_state(user: Optional[Dict[str, Any]]) -> str:
    """'ok' | 'missing' | 'disabled' | 'not_admin' — может ли владелец пользоваться токеном."""
    if user is None:
        return 'missing'
    if not user.get('active'):
        return 'disabled'
    if not user.get('is_admin'):
        return 'not_admin'
    return 'ok'


def _status(row: Dict[str, Any]) -> str:
    if row.get('revoked_at'):
        return 'revoked'
    expires = row.get('expires_at')
    if expires:
        try:
            if datetime.fromisoformat(expires) <= _now():
                return 'expired'
        except ValueError:
            return 'expired'   # нечитаемый срок — безопаснее считать истёкшим
    return 'active'


def create(user: Dict[str, Any], name: str, domains: Any = None,
           expires_days: Optional[int] = None, mode: str = 'full') -> Tuple[str, Dict[str, Any]]:
    """Выпустить токен владельцу user (запись аккаунта из auth_manager).

    mode — режим доступа токена (read | draft | full). Возвращает (токен_целиком,
    строка_списка). Токен целиком больше нигде не хранится.
    Ошибки ввода -> ValueError с русским текстом.
    """
    if not user or user.get('id') is None:
        raise ValueError('Не указан владелец токена')
    name = (name or '').strip()
    if not name:
        raise ValueError('Дайте токену имя — например, «Claude Code, ноутбук»')
    if len(name) > NAME_MAX:
        raise ValueError(f'Имя токена длиннее {NAME_MAX} символов')
    picked = normalize_domains(domains)
    picked_mode = normalize_mode(mode)
    expires_at = None
    if expires_days not in (None, '', 0, '0'):
        try:
            days = int(expires_days)
        except (TypeError, ValueError):
            raise ValueError('Срок действия — число дней')
        if days < 1 or days > MAX_EXPIRES_DAYS:
            raise ValueError(f'Срок действия — от 1 до {MAX_EXPIRES_DAYS} дней (или без срока)')
        expires_at = (_now() + timedelta(days=days)).isoformat()
    raw = TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_RANDOM_BYTES)
    token_id = 'st_' + secrets.token_hex(8)
    now = _now().isoformat()
    _ensure()
    with db.write() as conn:
        conn.execute(
            'INSERT INTO static_tokens (id, token_hash, prefix, name, domains, user_id, user_login, '
            'created_at, created_by, expires_at, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (token_id, hash_token(raw), raw[:PREFIX_CHARS], name, json.dumps(picked), int(user['id']),
             user.get('login') or '', now, user.get('login') or '', expires_at, picked_mode))
        row = conn.execute('SELECT * FROM static_tokens WHERE id=?', (token_id,)).fetchone()
    return raw, _row_public(row)


# Статус строки списка, если сам токен действует, но владелец не может им пользоваться.
OWNER_STATUSES = {'missing': 'owner_missing', 'disabled': 'owner_disabled', 'not_admin': 'owner_not_admin'}


def list_tokens(include_revoked: bool = True) -> List[Dict[str, Any]]:
    """Все токены, новые сверху (без хэшей), с состоянием владельца.

    Поля владельца: owner_state ('ok' | 'missing' | 'disabled' | 'not_admin' | 'unknown'),
    owner_login, owner_display_name, owner_active, owner_admin. token_status — статус самого
    токена (active | revoked | expired); status — что показать: для действующего токена
    неработающего владельца — owner_missing | owner_disabled | owner_not_admin.
    """
    _ensure()
    sql = 'SELECT * FROM static_tokens'
    if not include_revoked:
        sql += ' WHERE revoked_at IS NULL'
    sql += ' ORDER BY created_at DESC, rowid DESC'      # rowid — порядок выпуска внутри секунды
    with db.read() as conn:
        rows = [_row_public(r) for r in conn.execute(sql).fetchall()]
    users: Dict[int, Any] = {}
    try:
        from core.auth_manager import get_auth_manager
        manager = get_auth_manager()
    except Exception:  # noqa: BLE001 — список токенов открывается и без базы аккаунтов
        manager = None
    for row in rows:
        uid = int(row['user_id'])
        if uid not in users:
            try:
                users[uid] = manager.get_by_id(uid) if manager is not None else 'unknown'
            except Exception:  # noqa: BLE001
                users[uid] = 'unknown'
        user = users[uid]
        row['token_status'] = row['status']
        if user == 'unknown':
            row.update(owner_state='unknown', owner_login=row['user_login'], owner_display_name=None,
                       owner_active=None, owner_admin=None)
            continue
        state = _owner_state(user)
        row.update(owner_state=state, owner_login=(user or {}).get('login') or row['user_login'],
                   owner_display_name=(user or {}).get('display_name'),
                   owner_active=bool(user and user.get('active')), owner_admin=bool(user and user.get('is_admin')))
        if row['status'] == 'active' and state != 'ok':
            row['status'] = OWNER_STATUSES[state]
    return rows


# Имя из контракта (tokens.list()). Встроенный список внутри модуля — _builtin_list.
list = list_tokens   # noqa: A001


def get(token_id: str) -> Optional[Dict[str, Any]]:
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT * FROM static_tokens WHERE id=?', (token_id,)).fetchone()
    return _row_public(row) if row else None


def revoke(token_id: str, by: str = '') -> bool:
    """Отозвать токен. True — отозван сейчас; False — нет такого или уже отозван."""
    _ensure()
    with db.write() as conn:
        cur = conn.execute('UPDATE static_tokens SET revoked_at=?, revoked_by=? '
                           'WHERE id=? AND revoked_at IS NULL',
                           (_now().isoformat(), by or '', token_id))
        return cur.rowcount > 0


def revoke_all_for_user(user_id: int, by: str = '') -> int:
    """Отозвать все действующие токены владельца. Возвращает число отозванных.

    Зовёт routes/auth.py при удалении аккаунта, его отключении и снятии флага
    администратора: иначе возврат флага снова оживил бы старые токены.
    """
    _ensure()
    with db.write() as conn:
        cur = conn.execute('UPDATE static_tokens SET revoked_at=?, revoked_by=? '
                           'WHERE user_id=? AND revoked_at IS NULL',
                           (_now().isoformat(), by or '', int(user_id)))
        return cur.rowcount


def verify_static(raw: Optional[str]) -> Optional[Principal]:
    """Проверить статический токен. Principal — действует; None — не наш, отозван или истёк."""
    if not raw or not isinstance(raw, str) or not raw.startswith(TOKEN_PREFIX):
        return None
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT * FROM static_tokens WHERE token_hash=?', (hash_token(raw),)).fetchone()
    if row is None:
        return None
    data = dict(row)
    if _status(data) != 'active':
        return None
    now = _now()
    last = data.get('last_used_at')
    stale = True
    if last:
        try:
            stale = (now - datetime.fromisoformat(last)).total_seconds() >= LAST_USED_EVERY_S
        except ValueError:
            stale = True
    if stale:
        with db.write() as conn:
            conn.execute('UPDATE static_tokens SET last_used_at=? WHERE id=?', (now.isoformat(), data['id']))
    domains: Sequence[str] = tuple(json.loads(data['domains'] or '[]')) or (ALL_DOMAINS,)
    return Principal(user_id=int(data['user_id']), login=data['user_login'], display_name=data['user_login'],
                     token_id=data['id'], token_kind='static', client_name=data['name'],
                     domains=tuple(domains), expires_at=data.get('expires_at'),
                     mode=data.get('mode') or 'full')

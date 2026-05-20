"""Ежедневная проверка открытых смен в 4 барах KULT.

Вызывается из core/open_check_scheduler.py в 14:59 МСК и из админ-эндпоинта
routes/open_check.py для ручного теста.

Состояние "бар открыт на момент check_dt" = в iiko есть кассовая смена со
status=OPEN, чей pointOfSaleId маппится в имя бара через get_groups_with_pos(),
и openDate <= check_dt (МСК).

Диапазон запроса — yesterday..today, потому что ночная смена, открытая вчера и
ещё не закрытая, имеет openDate=вчера; без yesterday она потерялась бы.

Получатели = env-переменные ПЛЮС чаты, подключённые кнопками в самом боте
(core/open_check_subscribers.py):
- "всё открыто"  → TELEGRAM_GROUP_CHAT_ID + подписчики 'positive'
- тревоги/ошибки → TELEGRAM_ALARM_CHAT_IDS + подписчики 'alarm'

Матрица результата → действие:
- iiko_error=True         → получатели тревог: [Open-check ERROR]
- closed_keys == []       → получатели "всё открыто": [Open-check]
- closed_keys != []       → получатели тревог: [Open-check ALARM]
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from core.iiko_api import IikoAPI
from core.employee_plans import BAR_NAME_MAPPING, normalize_bar_name
from core.venues_config import KEY_TO_IIKO_NAME, PHYSICAL_VENUES

# Имена точек в кассовых сменах (corporation/groups) НЕ совпадают с OLAP
# Store.Name: например, "Пивная культура" в сменах = Кременчугская, есть и
# "Планерная" (новая точка). Поэтому маппинг берём из employee_plans.BAR_NAME_MAPPING,
# а не из venues_config.IIKO_NAME_TO_KEY (тот построен под OLAP-имена).

MOSCOW_TZ = timezone(timedelta(hours=3))

log = logging.getLogger("open-check")


def now_msk() -> datetime:
    """Текущее время в Москве (naive, чтобы совпадать с _parse_iso_datetime)."""
    return datetime.now(MOSCOW_TZ).replace(tzinfo=None)


def _env_chat_ids(var_name: str) -> List[str]:
    """Разобрать env-список chat_id через запятую."""
    raw = os.environ.get(var_name, '')
    return [s.strip() for s in raw.split(',') if s.strip()]


def _is_dry_run() -> bool:
    return os.environ.get('OPEN_CHECK_DRY_RUN', '').lower() in ('1', 'true', 'yes', 'on')


def check_bars_state(
    check_dt: datetime,
    api_factory: Callable[[], IikoAPI] = IikoAPI,
) -> dict:
    """Опросить iiko и сказать, какие из 4 баров открыты на момент check_dt.

    Args:
        check_dt: момент проверки (naive МСК).
        api_factory: фабрика IikoAPI (DI для тестов).

    Returns dict со стабильной схемой:
        {
            'iiko_error': bool,
            'error_msg': str | None,
            'open_keys': set[str],     # подмножество PHYSICAL_VENUES (4 бара)
            'closed_keys': list[str],  # PHYSICAL_VENUES минус open_keys, в порядке PHYSICAL_VENUES
            'other_open': list[str],   # открытые точки вне 4 баров (например planernaya)
            'unknown_pos': list[str],  # имена POS из iiko, которые не маппятся вообще
            'check_dt': datetime,
        }
    """
    today = check_dt.strftime('%Y-%m-%d')
    yesterday = (check_dt - timedelta(days=1)).strftime('%Y-%m-%d')

    def _error(msg: str) -> dict:
        return {
            'iiko_error': True,
            'error_msg': msg,
            'open_keys': set(),
            'closed_keys': list(PHYSICAL_VENUES),
            'other_open': [],
            'unknown_pos': [],
            'check_dt': check_dt,
        }

    api = api_factory()
    if not api.authenticate():
        return _error('auth_failed')

    try:
        try:
            pos_map = api.get_groups_with_pos()
            shifts = api.get_cash_shifts(yesterday, today, status='OPEN')
        except Exception as e:
            log.exception("iiko request failed")
            return _error(str(e))
    finally:
        api.logout()

    open_keys = set()
    other_open: List[str] = []
    unknown_pos: List[str] = []

    for sh in shifts or []:
        pos_id = sh.get('pointOfSaleId')
        if not pos_id:
            continue
        pos_name = pos_map.get(pos_id)
        if not pos_name:
            continue
        venue_key = BAR_NAME_MAPPING.get(normalize_bar_name(pos_name))
        if not venue_key:
            if pos_name not in unknown_pos:
                unknown_pos.append(pos_name)
            continue
        open_dt = api._parse_iso_datetime(sh.get('openDate', ''))
        if not (open_dt and open_dt <= check_dt):
            continue
        if venue_key in PHYSICAL_VENUES:
            open_keys.add(venue_key)
        elif venue_key not in other_open:
            other_open.append(venue_key)

    closed_keys = [k for k in PHYSICAL_VENUES if k not in open_keys]
    return {
        'iiko_error': False,
        'error_msg': None,
        'open_keys': open_keys,
        'closed_keys': closed_keys,
        'other_open': other_open,
        'unknown_pos': unknown_pos,
        'check_dt': check_dt,
    }


def _fmt_time(check_dt: datetime) -> str:
    return check_dt.strftime('%H:%M')


def _key_to_name(key: str) -> str:
    return KEY_TO_IIKO_NAME.get(key) or key


def format_positive_message(check_dt: datetime) -> str:
    names = ', '.join(_key_to_name(k) for k in PHYSICAL_VENUES)
    return f"[Open-check] {_fmt_time(check_dt)} МСК. Все 4 бара открыты: {names}."


def format_alarm_message(state: dict, check_dt: datetime) -> str:
    closed = ', '.join(_key_to_name(k) for k in state['closed_keys'])
    open_list = [k for k in PHYSICAL_VENUES if k in state['open_keys']]
    open_txt = ', '.join(_key_to_name(k) for k in open_list) if open_list else 'нет'
    return (
        f"[Open-check ALARM] {_fmt_time(check_dt)} МСК. "
        f"Закрыты: {closed}. Открыты: {open_txt}."
    )


def format_iiko_error_message(state: dict, check_dt: datetime) -> str:
    err = state.get('error_msg') or 'unknown_error'
    return (
        f"[Open-check ERROR] {_fmt_time(check_dt)} МСК. "
        f"iiko недоступен: {err}. Проверка не выполнена."
    )


def _dedupe(items: List[str]) -> List[str]:
    seen, out = set(), []
    for x in items:
        x = str(x).strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _positive_recipients() -> List[str]:
    """Кому слать "всё открыто": env TELEGRAM_GROUP_CHAT_ID + подписчики 'positive'."""
    from core import open_check_subscribers as subs
    env = []
    g = os.environ.get('TELEGRAM_GROUP_CHAT_ID', '').strip()
    if g:
        env.append(g)
    return _dedupe(env + subs.get_recipients('positive'))


def _alarm_recipients() -> List[str]:
    """Кому слать тревоги/ошибки: env TELEGRAM_ALARM_CHAT_IDS + подписчики 'alarm'."""
    from core import open_check_subscribers as subs
    return _dedupe(_env_chat_ids('TELEGRAM_ALARM_CHAT_IDS') + subs.get_recipients('alarm'))


def send_report(state: dict, check_dt: datetime) -> dict:
    """Отправить отчёт по матрице (синхронно, через Telegram HTTP API).

    DRY-RUN режим (env OPEN_CHECK_DRY_RUN=1): сообщение уходит только первому
    получателю (тревог, иначе позитива) с префиксом [DRY-RUN].
    """
    token = os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN')
    if not token:
        log.error("TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан — отправка пропущена")
        return {'sent': 0, 'skipped': True, 'reason': 'no_token'}

    dry_run = _is_dry_run()

    if state['iiko_error']:
        text = format_iiko_error_message(state, check_dt)
        recipients = _alarm_recipients()
        target = 'alarm'
    elif not state['closed_keys']:
        text = format_positive_message(check_dt)
        recipients = _positive_recipients()
        target = 'positive'
    else:
        text = format_alarm_message(state, check_dt)
        recipients = _alarm_recipients()
        target = 'alarm'

    if dry_run:
        text = '[DRY-RUN] ' + text
        first = recipients[:1] or _alarm_recipients()[:1] or _positive_recipients()[:1]
        recipients = first
        target = 'dry-run'

    if not recipients:
        log.warning("Нет получателей (target=%s, dry_run=%s) — текст: %s", target, dry_run, text)
        return {'sent': 0, 'skipped': True, 'reason': 'no_recipients',
                'target': target, 'text': text}

    from core.open_check_telegram import send_message
    sent = 0
    for chat_id in recipients:
        if send_message(chat_id, text):
            sent += 1

    log.info("send_report target=%s dry_run=%s sent=%d/%d text=%r",
             target, dry_run, sent, len(recipients), text)
    return {
        'sent': sent,
        'recipients': len(recipients),
        'skipped': False,
        'target': target,
        'dry_run': dry_run,
        'text': text,
    }


def run_check(check_dt: Optional[datetime] = None) -> dict:
    """Sync-обёртка для шедулера и admin-endpoint.

    Не делает lock — это ответственность шедулера. Admin-endpoint с force=1
    всегда хочет запуск, и lock-логика к нему не применяется.
    """
    if check_dt is None:
        check_dt = now_msk()

    state = check_bars_state(check_dt)
    if state.get('other_open'):
        log.info("открыты точки вне 4 баров: %s", state['other_open'])
    if state['unknown_pos']:
        log.info("unknown_pos в iiko (не маппятся): %s", state['unknown_pos'])

    report = send_report(state, check_dt)

    return {
        'check_dt': check_dt.isoformat(),
        'state': {
            'iiko_error': state['iiko_error'],
            'error_msg': state['error_msg'],
            'open_keys': sorted(state['open_keys']),
            'closed_keys': state['closed_keys'],
            'other_open': state.get('other_open', []),
            'unknown_pos': state['unknown_pos'],
        },
        'report': report,
    }

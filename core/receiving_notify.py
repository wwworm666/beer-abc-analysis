"""Приёмка на РЦ: сообщение бухгалтерии в Telegram «приёмка ждёт разбора».

Что это. Когда фоновая обработка закрытой приёмки (core/receiving_service.py)
открывает строки разбора, которые требуют работы в iiko — новая позиция, похожая
карточка, удалённая или архивная карточка, — бухгалтерия получает одно сообщение:
номер приёмки, кто и когда её закрыл, сколько принято, счёт по статусам, до
MAX_LISTED позиций и ссылку на страницу разбора с фильтром этой приёмки. Дубли
штрихкода сами по себе сообщение не вызывают (карточка есть, приёмка не стоит),
но в счёт и список попадают, если сообщение всё равно уходит.

Почему отдельная аудитория. Бот тот же, что у проверки открытия смен
(kulturaopenclosed, токен TELEGRAM_OPEN_CHECK_BOT_TOKEN), но получатели — только
чаты из RECEIVING_NOTIFY_CHAT_IDS. Подписчики бота кнопкой «Подписаться» сюда не
входят: подписаться может кто угодно (docs/lessons.md «Бот, на который может
подписаться любой»), а разбор приёмок нужен только бухгалтерии. Бухгалтер один раз
открывает бота и нажимает /start: без этого Telegram не даёт боту написать первым.

Как. Отправка — open_check_bot._send_with_retries (два прохода, обход блокировки
ТСПУ); чаты, до которых не дошло, — в очередь досылки core/open_check_pending.py
(target 'receiving', досылается до конца дня с пометкой о задержке). Отправка
может занять минуты, поэтому обработка приёмки зовёт notify_receipt_in_background.
Ничего не шлётся (ответ skipped с причиной), если RECEIVING_NOTIFY=0 ('disabled'),
нет токена бота ('no_token'), нет чатов ('no_recipients') или в строках нет
позиций к разбору ('nothing_to_report'). OPEN_CHECK_DRY_RUN=1 — как у отчётов
бота: только первому чату, с пометкой [DRY-RUN], без очереди досылки.

Формат — HTML (parse_mode=HTML): каждое значение из данных (названия ЧЗ, имя
закрывшего) проходит html.escape. Эмодзи нет (правило проекта).
Документация: docs/receiving.md.
"""
import html
import os
import threading
from typing import Callable, List, Optional

from core import msk_time

# id чатов бухгалтерии через запятую (бот kulturaopenclosed); пусто — никому.
ENV_CHATS = 'RECEIVING_NOTIFY_CHAT_IDS'
# '0' — не слать вовсе (по умолчанию шлём, если заданы токен и чаты).
ENV_SWITCH = 'RECEIVING_NOTIFY'
# Адрес сайта для ссылки (как core/review_notify.SITE: API_BASE_URL читают только
# маршруты open-check, а ссылка в сообщении должна быть боевой и в DRY-RUN).
SITE = 'https://beerkultura.ru'
# Сколько позиций перечислить: 10 строк читаются с телефона без прокрутки;
# остальные — одной строкой «и ещё N» со ссылкой на страницу.
MAX_LISTED = 10
# Название ЧЗ в строке списка: до 100 знаков (полное — на странице). 10 строк по
# ~130 знаков с заголовком — далеко от предела Telegram 4096 знаков.
NAME_LEN = 100
# Метка очереди досылки (core/open_check_pending: только для логов).
QUEUE_TARGET = 'receiving'

# Статусы, ради которых бухгалтерии стоит писать: в iiko надо завести или вернуть
# карточку. duplicate — нет: карточка есть, приёмку это не останавливает.
NOTIFY_STATUSES = ('new', 'similar', 'restore')
# Порядок и подписи статусов в сообщении (раздел 1 docs/receiving.md: важные выше).
STATUS_ORDER = ('new', 'similar', 'restore', 'duplicate')
STATUS_LABELS = {
    'new': 'новая',
    'similar': 'похожая карточка',
    'restore': 'удалена или в архиве',
    'duplicate': 'дубль штрихкода',
}
# Счёт по статусам: «новых 2, похожих 1, восстановить 1, дублей 1».
STATUS_COUNT_WORDS = {
    'new': 'новых',
    'similar': 'похожих',
    'restore': 'восстановить',
    'duplicate': 'дублей',
}
MONTHS_GEN = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
              'сентября', 'октября', 'ноября', 'декабря')

_LOG = '[RECEIVING-NOTIFY]'


# ----------------------------------------------------------------- получатели и выключатели

def recipients() -> List[str]:
    """Чаты бухгалтерии из RECEIVING_NOTIFY_CHAT_IDS, без повторов, в порядке записи."""
    from core.open_check_bot import _env_chat_ids
    out = []
    for chat in _env_chat_ids(ENV_CHATS):
        if chat not in out:
            out.append(chat)
    return out


def _is_dry_run() -> bool:
    """OPEN_CHECK_DRY_RUN — общий тестовый режим бота (как core/review_notify)."""
    return os.environ.get('OPEN_CHECK_DRY_RUN', '').lower() in ('1', 'true', 'yes', 'on')


def _switched_off() -> Optional[str]:
    """Причина не слать ('disabled' | 'no_token') или None."""
    if os.environ.get(ENV_SWITCH, '1').strip() == '0':
        return 'disabled'
    if not os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN', '').strip():
        return 'no_token'
    return None


# ----------------------------------------------------------------- текст

def _fmt_when(value) -> str:
    """'2026-10-03T14:05:00+03:00' -> '3 октября 2026, 14:05'; нечитаемое -> ''."""
    text = str(value or '')
    try:
        year, month, day = int(text[:4]), int(text[5:7]), int(text[8:10])
        hhmm = text[11:16]
        if not (1 <= month <= 12) or len(hhmm) != 5:
            return ''
    except ValueError:
        return ''
    return f'{day} {MONTHS_GEN[month - 1]} {year}, {hhmm}'


def _cut(text: str, limit: int) -> str:
    text = ' '.join(str(text or '').split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _row_qty(row: dict, receipt_id) -> int:
    """Штук этого GTIN в ЭТОЙ приёмке (row['receipts']); нет разбивки — row['qty'] за все."""
    for item in row.get('receipts') or ():
        if isinstance(item, dict) and _int(item.get('id')) == _int(receipt_id):
            return _int(item.get('qty'))
    return _int(row.get('qty'))


# «Новая» без названия ЧЗ: похожую карточку искать было не по чему (бар-ПК недоступен,
# chz.py устарел, в каталоге ЧЗ карточки нет) — бухгалтеру сначала найти в iiko по
# штрихкоду или поставщику, а не заводить сразу (риск дубля, ревью 2026-10-03).
NO_NAME_NOTE = 'нет названия ЧЗ, похожие не проверены'


def _has_name(row: dict) -> bool:
    chz = row.get('chz') if isinstance(row.get('chz'), dict) else {}
    return bool(chz.get('name') or chz.get('full_name'))


def _pack_units(row: dict) -> str:
    """Мультипак (ЧЗ: групповая упаковка) — сколько единиц в ней, иначе ''."""
    chz = row.get('chz') if isinstance(row.get('chz'), dict) else {}
    return str(chz.get('pack_units') or '') if chz.get('main_gtin') else ''


def _row_title(row: dict) -> str:
    """Название из ЧЗ, иначе GTIN (у позиции без данных ЧЗ другого имени нет)."""
    chz = row.get('chz') if isinstance(row.get('chz'), dict) else {}
    name = _cut(chz.get('name') or chz.get('full_name') or '', NAME_LEN)
    return name or str(row.get('gtin') or '')


def _review_rows(rows) -> list:
    """Строки, о которых пишем: словари со статусом из STATUS_ORDER (found не пишем)."""
    return [r for r in (rows or ()) if isinstance(r, dict) and r.get('status') in STATUS_ORDER]


def format_receipt_message(receipt, rows) -> str:
    """Сообщение «приёмка ждёт разбора» (HTML, всё из данных — через html.escape).

    receipt — receipt dict (core/receiving_store), rows — review rows, открытые этой
    приёмкой. Строки со статусом вне STATUS_ORDER (found) не учитываются.
    Список: сначала важные статусы (новая, похожая, восстановить, дубль), внутри —
    по штукам в этой приёмке по убыванию, затем по названию.
    """
    receipt = receipt if isinstance(receipt, dict) else {}
    rid = _int(receipt.get('id'))
    picked = _review_rows(rows)
    lines = [f'<b>Приёмка на РЦ №{rid}: нужен разбор</b>']

    when = _fmt_when(receipt.get('closed_at'))
    who = str(receipt.get('closed_by') or '').strip()
    closed = ', '.join(part for part in (when, who) if part)
    if closed:
        lines.append('Закрыта: ' + html.escape(closed))
    counts = receipt.get('counts') if isinstance(receipt.get('counts'), dict) else {}
    lines.append(f'Принято: {_int(counts.get("units"))} шт., позиций: {_int(counts.get("gtins"))}')

    by_status = {s: 0 for s in STATUS_ORDER}
    for row in picked:
        by_status[row['status']] += 1
    parts = [f'{STATUS_COUNT_WORDS[s]} {by_status[s]}' for s in STATUS_ORDER if by_status[s]]
    if parts:
        lines.append('К разбору: ' + ', '.join(parts))

    order = {s: i for i, s in enumerate(STATUS_ORDER)}
    listed = sorted(picked, key=lambda r: (order[r['status']], -_row_qty(r, rid),
                                           _row_title(r).casefold(), str(r.get('gtin') or '')))
    if listed:
        lines.append('')
    for row in listed[:MAX_LISTED]:
        label = STATUS_LABELS[row['status']]
        if row['status'] == 'new' and not _has_name(row):
            label += ' (' + NO_NAME_NOTE + ')'
        units = _pack_units(row)
        if units:
            label += ' (групповая упаковка по ' + units + ' шт.)'
        lines.append(f'- {html.escape(_row_title(row))} — {label}, {_row_qty(row, rid)} шт.')
    rest = len(listed) - MAX_LISTED
    if rest > 0:
        lines.append(f'И ещё {rest} — на странице разбора.')
    lines.append('')
    lines.append(f'{SITE}/receiving/review?receipt={rid}')
    return '\n'.join(lines)


# ----------------------------------------------------------------- отправка

def _default_send(chats: List[str], text: str) -> dict:
    from core.open_check_bot import _send_with_retries
    return _send_with_retries(chats, text)


def _default_queue(date_str: str, text: str, chats: List[str], first_try: str) -> None:
    from core import open_check_pending
    open_check_pending.add(date_str=date_str, text=text, chats=chats, target=QUEUE_TARGET,
                           first_try=first_try)


def notify_receipt(receipt, rows, *, send: Optional[Callable] = None,
                   queue: Optional[Callable] = None, chats: Optional[List[str]] = None) -> dict:
    """Отправить бухгалтерии сообщение о приёмке. -> {'sent', 'failed', 'skipped'}.

    sent — скольким чатам доставлено; failed — chat_id, до которых не дошло (вне
    DRY-RUN они в очереди досылки); skipped — причина, если ничего не слали
    ('disabled' | 'no_token' | 'no_recipients' | 'nothing_to_report' — среди строк
    нет ни одной со статусом из NOTIFY_STATUSES), иначе None.
    send(chats, text) -> {'sent', 'failed'}; queue(date_str, text, chats, first_try);
    chats — список получателей вместо RECEIVING_NOTIFY_CHAT_IDS (DI для тестов).
    """
    summary = {'sent': 0, 'failed': [], 'skipped': None}
    reason = _switched_off()
    if reason:
        summary['skipped'] = reason
        return summary
    targets = list(chats) if chats is not None else recipients()
    if not targets:
        summary['skipped'] = 'no_recipients'
        return summary
    if not any(r['status'] in NOTIFY_STATUSES for r in _review_rows(rows)):
        summary['skipped'] = 'nothing_to_report'
        return summary

    text = format_receipt_message(receipt, rows)
    dry = _is_dry_run()
    if dry:
        targets = targets[:1]
        text = '[DRY-RUN] ' + text
    result = (send or _default_send)(targets, text) or {}
    summary['sent'] = _int(result.get('sent'))
    summary['failed'] = [str(c) for c in (result.get('failed') or [])]
    if summary['failed'] and not dry:
        now = msk_time.now()
        (queue or _default_queue)(now.strftime('%Y-%m-%d'), text, summary['failed'],
                                  now.strftime('%H:%M'))
    return summary


def notify_receipt_in_background(receipt, rows) -> threading.Thread:
    """notify_receipt в фоновом потоке: обработка приёмки не ждёт Telegram.

    Итог и сбой — в лог сервера (chat_id недоставленных там же, как у open_check_bot).
    """
    rid = _int(receipt.get('id')) if isinstance(receipt, dict) else 0

    def run():
        try:
            result = notify_receipt(receipt, rows)
            print(f'{_LOG} приёмка №{rid}: {result}')
        except Exception as e:  # noqa: BLE001 — фоновый поток не должен падать молча
            print(f'{_LOG} приёмка №{rid}: сообщение не отправлено: {type(e).__name__}: {e}')

    thread = threading.Thread(target=run, name=f'receiving-notify-{rid}', daemon=True)
    thread.start()
    return thread

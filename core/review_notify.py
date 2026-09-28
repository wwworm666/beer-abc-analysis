"""Новые отзывы — в Telegram-бот kulturaopenclosed (бот проверки открытых смен).

Решение владельца 2026-09-28: «дублируй туда все новые отзывы». Каждый новый
отзыв уходит отдельным сообщением тем, кто подписался в боте кнопкой
«Подписаться» (core/open_check_subscribers.py — «подписчик получает всё»).
Групповой чат смены (TELEGRAM_GROUP_CHAT_ID) отзывы не получает: там бармены,
а отзывы бывают резкими — это решает владелец.

Три пути отправки:
- отзывы Яндекса — после ежедневной сверки (core/yandex_reviews_sync.py зовёт
  notify_new_reviews);
- отзыв из гостевого бота @kult_taplist_bot — СРАЗУ после сохранения
  (core/taplist_polling.py зовёт notify_review_in_background -> notify_review_now);
- подбор пропущенных отзывов из бота — раз в SWEEP_INTERVAL_SEC (10 минут) из цикла
  опроса бота (notify_pending_in_background -> notify_pending_bot_reviews): отзыв,
  о котором сразу не сообщили (воркер перезапустился сразу после сохранения, не было
  подписчиков, упёрлись в потолок), иначе ждал бы сверки Яндекса — а она не
  запускается без cookies, при истёкшем входе и капче (проверка 2026-09-28).

Что считается новым отзывом: загруженный (origin 'import' — из Яндекса или из
бота) и ещё не отправленный (нет tg_notified_at); для ежедневного пути — ещё и
добавленный в хранилище не раньше notify_since (начало первой сверки с
уведомлениями: 358 отзывов истории не рассылаются); для подбора — добавленный за
последние PENDING_WINDOW_HOURS (72 часа: старше — уже есть на сайте, лавину после
долгого простоя не шлём). Отметка tg_notified_at в самом отзыве — повтор не шлёт дубль.

Без дублей между путями: все держат одну блокировку рассылки (_notify_lock:
threading.Lock процесса + межпроцессный file_lock(<файл отзывов>.notify.lock))
на всё «выбрать -> отправить -> отметить».

Личные данные (проверка 2026-09-28). Подписаться на бот персонала может любой
(подписка одной кнопкой без списка допуска — решение владельца, здесь не меняется),
поэтому об отзыве из бота туда уходят ТОЛЬКО бар, оценка, дата и ссылка на страницу
отзывов — без имени, ника, телефона и текста (format_review, format_latest). Отзывы
Яндекса — полностью: они и так публичны на Яндекс Картах.

Потолок для отзывов из бота (защита от спама): не больше NOTIFY_BOT_PER_HOUR (20)
отзывов в час по отметкам tg_notified_at. Сверх — немедленная отправка пропускается
(skipped 'rate_limited'), а подбор шлёт все накопившиеся одной сводкой со ссылкой.

Отправка — тем же транспортом, что отчёты бота (open_check_bot._send_with_retries:
два прохода, обход блокировки ТСПУ); чаты, до которых не дошло, — в очередь
досылки core/open_check_pending.py (досылается до конца дня с пометкой о
задержке). Отзыв отмечается отправленным, если хоть кому-то доставлен или
поставлен в очередь.

Предохранитель сверки: за раз не больше NOTIFY_MAX_PER_RUN сообщений; остальные —
одной сводкой со ссылкой на страницу и тоже отмечаются.

Без токена бота или без подписчиков ничего не шлётся и не отмечается — отзывы
уйдут, когда появятся токен или подписчик. OPEN_CHECK_DRY_RUN=1 — как у отчётов
бота: только первому получателю, с пометкой [DRY-RUN]. YANDEX_REVIEWS_NOTIFY=0 —
не слать вовсе: ежедневный путь проверяет планировщик
(core/yandex_reviews_scheduler.py), немедленный и подбор — сами.

Формат — HTML (parse_mode=HTML), весь текст отзыва экранируется html.escape.
Эмодзи нет (правило проекта). Документация: docs/yandex-reviews.md, docs/reviews.md.
"""
import html
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Callable, Iterable, List, Optional

from core.guest_reviews import BARS, RATING_BUCKETS

# Предохранитель от лавины: больше — одной сводкой (см. докстринг).
NOTIFY_MAX_PER_RUN = 10
# Отзывы из бота: не больше стольких в час по отдельности, сверх — сводкой (спам).
NOTIFY_BOT_PER_HOUR = 20
# Подбор пропущенных отзывов из бота: как часто (зовёт цикл опроса бота) и за какой срок.
SWEEP_INTERVAL_SEC = 600
PENDING_WINDOW_HOURS = 72
# Текст отзыва в сообщении: предел Telegram 4096 знаков на сообщение, 1500 —
# с запасом на заголовок и ответ; длиннее — обрезка с «…» и ссылка на страницу.
TEXT_PREVIEW_LEN = 1500
REPLY_PREVIEW_LEN = 300
# Сколько ждать блокировку рассылки. Ежедневная сверка держит её, пока шлёт до
# NOTIFY_MAX_PER_RUN + 1 сообщений с повторами; при лежащем Telegram это минуты
# (до ~45 с на провальную отправку, open_check_bot.SEND_PASSES). 10 минут — с
# запасом; дольше — немедленная отправка сдаётся, отзыв подберёт следующий подбор.
NOTIFY_LOCK_TIMEOUT = 600
SITE = 'https://beerkultura.ru'
SOURCE_NAMES = {'yandex': 'Яндекс Карты', 'bot': 'Бот'}
MONTHS_GEN = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
              'сентября', 'октября', 'ноября', 'декабря')
BAR_NAMES = {b['key']: b['name'] for b in BARS}
BOT_REVIEWS_URL = SITE + '/reviews?source=bot&month=all'
# Строка вместо текста и контактов отзыва из бота (бот персонала открыт для подписки).
BOT_PRIVATE_NOTE = 'Текст, имя и контакты гостя — только на сайте, в этот бот они не отправляются.'
STAMP = '%Y-%m-%dT%H:%M'

_notify_guard = threading.Lock()
_sweep_guard = threading.Lock()


def _fmt_when(dt: Optional[str]) -> str:
    """'2026-09-27T18:30' -> '27 сентября 2026, 18:30'."""
    if not dt or len(dt) < 16:
        return ''
    y, m, d = int(dt[:4]), int(dt[5:7]), int(dt[8:10])
    return f'{d} {MONTHS_GEN[m - 1]} {y}, {dt[11:16]}'


def _cut(text: str, limit: int) -> str:
    text = (text or '').strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _shift(now_str: str, minutes: int) -> str:
    """'YYYY-MM-DDTHH:MM' + minutes -> та же форма (для сравнения строк отметок)."""
    return (datetime.strptime(now_str[:16], STAMP) + timedelta(minutes=minutes)).strftime(STAMP)


def _now_str() -> str:
    from core import msk_time
    return msk_time.now().strftime(STAMP)


@contextmanager
def _notify_lock(store):
    """Одна рассылка отзывов за раз — в процессе и между воркерами (см. докстринг).

    Не дождались за NOTIFY_LOCK_TIMEOUT -> TimeoutError / исключение portalocker:
    вызывающий ничего не отправляет и не отмечает.
    """
    if not _notify_guard.acquire(timeout=NOTIFY_LOCK_TIMEOUT):
        raise TimeoutError('рассылка отзывов занята дольше %d с' % NOTIFY_LOCK_TIMEOUT)
    try:
        path = getattr(store, 'data_file', None)
        if path:
            from core.json_store import file_lock
            with file_lock(path + '.notify.lock', timeout=NOTIFY_LOCK_TIMEOUT):
                yield
        else:
            yield
    finally:
        _notify_guard.release()


def candidates(reviews: Iterable[dict], since: str) -> List[dict]:
    """Новые отзывы для рассылки: загруженные, добавлены не раньше since, не отправлены.

    Порядок — по дате отзыва, затем id (детерминированно).
    """
    out = [r for r in reviews
           if r.get('origin') == 'import' and not r.get('tg_notified_at')
           and (r.get('added_at') or '') >= since]
    return sorted(out, key=lambda r: (r.get('created_at') or '', r.get('id') or ''))


def bot_sent_last_hour(reviews: Iterable[dict], now_str: str) -> int:
    """Сколько отзывов из бота отмечены отправленными за последние 60 минут (для потолка).

    Сводка отмечает все свои отзывы одним временем — они и считаются все: при спаме
    так и нужно, следующий подбор опять уйдёт сводкой.
    """
    lo = _shift(now_str, -60)
    return sum(1 for r in reviews
               if r.get('source') == 'bot' and lo <= str(r.get('tg_notified_at') or '') <= now_str[:16])


def _rating_word(rating) -> str:
    return f'оценка {rating} из 5' if isinstance(rating, int) else 'без оценки'


def _title(r: dict) -> str:
    rating = r.get('rating')
    lo, hi = RATING_BUCKETS['low']
    low = isinstance(rating, int) and lo <= rating <= hi
    return 'Новый отзыв — низкая оценка' if low else 'Новый отзыв'


def format_review(r: dict) -> str:
    """Сообщение об одном отзыве (HTML). Низкая оценка (1–2, как фильтр страницы) — в заголовке.

    Отзыв из бота — только бар, оценка, дата и ссылка (личные данные — докстринг модуля).
    """
    bar = BAR_NAMES.get(r.get('bar'), r.get('bar') or '')
    head = f'<b>{html.escape(_title(r))} · {html.escape(bar)}</b>'
    when = html.escape(_fmt_when(r.get('created_at')))
    if r.get('source') == 'bot':
        return '\n'.join([head, html.escape('Бот · ' + _rating_word(r.get('rating'))), when, '',
                          BOT_PRIVATE_NOTE, BOT_REVIEWS_URL])
    meta = [SOURCE_NAMES.get(r.get('source'), r.get('source') or ''), _rating_word(r.get('rating')),
            r.get('author') or 'без имени']
    lines = [head, html.escape(' · '.join(meta)), when]
    text = _cut(r.get('text') or '', TEXT_PREVIEW_LEN)
    lines.append('')
    lines.append(f'«{html.escape(text)}»' if text else 'Текста нет — только оценка.')
    lines.append('')
    reply = r.get('reply') if isinstance(r.get('reply'), dict) else None
    if r.get('status') == 'answered' and reply:
        lines.append('Ответ в Яндексе уже есть: «' + html.escape(_cut(reply.get('text') or '', REPLY_PREVIEW_LEN)) + '»')
        lines.append(f'{SITE}/reviews?month=all')
    else:
        lines.append('Ответа в Яндексе пока нет.')
        lines.append(f'{SITE}/reviews?status=new&month=all')
    return '\n'.join(lines)


def format_overflow(n: int) -> str:
    return (f'<b>Ещё {n} новых отзывов</b> — отдельными сообщениями не отправлены '
            f'(за раз не больше {NOTIFY_MAX_PER_RUN}).\n{SITE}/reviews?month=all')


def format_bot_overflow(n: int) -> str:
    """Сводка вместо отдельных сообщений, когда отзывов из бота больше потолка в час."""
    return (f'<b>Новых отзывов из бота: {n}</b> — отдельными сообщениями не отправлены '
            f'(не больше {NOTIFY_BOT_PER_HOUR} в час).\n{BOT_PRIVATE_NOTE}\n{BOT_REVIEWS_URL}')


# ----------------------------------------------------------------- кнопка «Последние отзывы»

# Кнопка и команда /reviews в меню бота (core/open_check_telegram.py, просьба
# владельца 2026-09-28): последние LATEST_COUNT отзывов по дате отзыва. Текст
# каждого — до LATEST_TEXT_LEN знаков: 5 × (заголовок + 300) укладывается в
# предел сообщения Telegram 4096 с запасом.
LATEST_COUNT = 5
LATEST_TEXT_LEN = 300
STATUS_WORDS = {'new': 'Ответа нет', 'answered': 'Ответ есть', 'skipped': 'Без ответа по решению'}


def format_latest(reviews: Iterable[dict], n: int = LATEST_COUNT) -> str:
    """Последние n отзывов (по дате отзыва, новые первыми; при равной — по id), HTML.

    В заголовке — сколько всего ждёт ответа (статус «Без ответа», за любую дату —
    как счётчик полосы «Требует внимания» на сайте). Отзыв из бота — «из бота», без
    имени и текста (личные данные — докстринг модуля).
    """
    items = list(reviews)
    waiting = sum(1 for r in items if r.get('status') == 'new')
    latest = sorted(items, key=lambda r: (r.get('created_at') or '', r.get('id') or ''), reverse=True)[:n]
    if not latest:
        return 'Отзывов пока нет.'
    lines = [f'<b>Последние {len(latest)} отзывов</b> · ждут ответа: {waiting}']
    for r in latest:
        rating = r.get('rating')
        bot = r.get('source') == 'bot'
        head = [BAR_NAMES.get(r.get('bar'), r.get('bar') or '')]
        if bot:
            head.append('из бота')
        head.append(f'{rating} из 5' if isinstance(rating, int) else 'без оценки')
        if not bot:
            head.append(r.get('author') or 'без имени')
        head.append(_fmt_when(r.get('created_at')))
        status = STATUS_WORDS.get(r.get('status'), '')
        if r.get('gone_at'):
            status += ' · нет в Яндексе'
        lines.append('')
        lines.append(f'<b>{html.escape(head[0])}</b> · ' + html.escape(' · '.join(head[1:])))
        if bot:
            lines.append('Текст и контакты — на сайте.')
        else:
            text = _cut(r.get('text') or '', LATEST_TEXT_LEN)
            lines.append(f'«{html.escape(text)}»' if text else 'Текста нет — только оценка.')
        lines.append(html.escape(status))
    lines.append('')
    lines.append(f'{SITE}/reviews?month=all')
    return '\n'.join(lines)


def latest_reviews_text() -> str:
    """Ответ кнопки «Последние отзывы»: читает хранилище отзывов; сбой — понятный текст."""
    try:
        from core.guest_reviews import get_review_store
        return format_latest(get_review_store().all())
    except Exception as e:  # noqa: BLE001 — бот не должен молчать
        print(f'[REVIEWS-BOT] последние отзывы: {e!r}')
        return 'Отзывы сейчас не читаются — откройте страницу отзывов на сайте.'


# ----------------------------------------------------------------- отправка

def _default_send(recipients: List[str], text: str) -> dict:
    from core.open_check_bot import _send_with_retries
    return _send_with_retries(recipients, text)


def _default_recipients() -> List[str]:
    from core import open_check_subscribers as subs
    return subs.get_recipients()


def _default_queue(date_str: str, text: str, chats: List[str], first_try: str) -> None:
    from core import open_check_pending
    open_check_pending.add(date_str=date_str, text=text, chats=chats, target='review', first_try=first_try)


def _is_dry_run() -> bool:
    return os.environ.get('OPEN_CHECK_DRY_RUN', '').lower() in ('1', 'true', 'yes', 'on')


def _switched_off(summary: dict) -> bool:
    """Выключатель и токен для немедленной отправки и подбора; причина — в summary['skipped']."""
    if os.environ.get('YANDEX_REVIEWS_NOTIFY', '1').strip() == '0':
        summary['skipped'] = 'disabled'
        return True
    if not os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN', '').strip():
        summary['skipped'] = 'no_token'
        return True
    return False


def _deliverer(chats: List[str], now_str: str, summary: dict, send: Callable, queue: Callable,
               dry: bool) -> Callable[[str], bool]:
    """deliver(text) -> отметить ли отзыв: доставлено хоть кому-то или (не в DRY-RUN)
    недоставленное поставлено в очередь досылки. Считает sent_messages / queued_chats."""
    def deliver(text: str) -> bool:
        if dry:
            text = '[DRY-RUN] ' + text
        res = send(chats, text) or {}
        sent, failed = res.get('sent', 0), list(res.get('failed') or [])
        if failed and not dry:
            queue(now_str[:10], text, failed, now_str[11:16])
            summary['queued_chats'] += len(failed)
        if sent:
            summary['sent_messages'] += 1
        return bool(sent) or bool(failed and not dry)
    return deliver


def notify_new_reviews(store, state: dict, now_str: str, *,
                       send: Optional[Callable] = None, recipients: Optional[Callable] = None,
                       queue: Optional[Callable] = None) -> dict:
    """Разослать новые отзывы подписчикам бота. Зовётся сверкой после загрузки.

    state — состояние сверки (здесь ставится notify_since при первом вызове);
    now_str — 'YYYY-MM-DDTHH:MM' по Москве (отметка tg_notified_at, дата очереди).
    send(recipients, text) -> {'sent', 'failed'}; recipients() -> [chat_id];
    queue(date_str, text, chats, first_try) — DI для тестов.
    Ответ — сводка для состояния сверки: candidates, sent_messages, queued_chats,
    overflow, skipped (no_token | no_recipients).
    Выбор кандидатов, отправка и отметка — под _notify_lock (без дублей с
    немедленной отправкой отзыва из бота и подбором).
    """
    since = state.setdefault('notify_since', state.get('started_at') or now_str)
    with _notify_lock(store):
        found = candidates(store.all(), since)
        summary = {'candidates': len(found), 'sent_messages': 0, 'queued_chats': 0, 'overflow': 0,
                   'skipped': None, 'since': since}
        if not found:
            return summary
        if not os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN', '').strip():
            summary['skipped'] = 'no_token'
            return summary
        chats = (recipients or _default_recipients)()
        if not chats:
            summary['skipped'] = 'no_recipients'
            return summary
        dry = _is_dry_run()
        if dry:
            chats = chats[:1]
        deliver = _deliverer(chats, now_str, summary, send or _default_send, queue or _default_queue, dry)

        marked = []
        for r in found[:NOTIFY_MAX_PER_RUN]:
            if deliver(format_review(r)):
                marked.append(r['id'])
        rest = found[NOTIFY_MAX_PER_RUN:]
        if rest:
            summary['overflow'] = len(rest)
            if deliver(format_overflow(len(rest))):
                marked.extend(r['id'] for r in rest)
        if marked:
            store.mark_notified(marked, now_str)
        return summary


def notify_review_now(store, review_id: str, now_str: Optional[str] = None, *,
                      send: Optional[Callable] = None, recipients: Optional[Callable] = None,
                      queue: Optional[Callable] = None) -> dict:
    """Сразу разослать один новый отзыв (отзыв из бота — владелец узнаёт сразу).

    Те же правила, транспорт, экранирование и отметка tg_notified_at, что у
    notify_new_reviews; под той же _notify_lock — сверка и подбор его не повторят.
    now_str — 'YYYY-MM-DDTHH:MM' по Москве (по умолчанию — сейчас).
    Ответ — {review_id, sent_messages, queued_chats, marked, skipped}; skipped:
    disabled (YANDEX_REVIEWS_NOTIFY=0) | no_token | not_found | not_import |
    already_sent | rate_limited (потолок NOTIFY_BOT_PER_HOUR) | no_recipients |
    None (отправляли). Не отмечен — подберёт подбор (notify_pending_bot_reviews).
    """
    summary = {'review_id': review_id, 'sent_messages': 0, 'queued_chats': 0, 'marked': False,
               'skipped': None}
    if _switched_off(summary):
        return summary
    now_str = now_str or _now_str()
    with _notify_lock(store):
        review = store.get(review_id)
        if review is None:
            summary['skipped'] = 'not_found'
            return summary
        if review.get('origin') != 'import':
            summary['skipped'] = 'not_import'
            return summary
        if review.get('tg_notified_at'):
            summary['skipped'] = 'already_sent'
            return summary
        if review.get('source') == 'bot' and bot_sent_last_hour(store.all(), now_str) >= NOTIFY_BOT_PER_HOUR:
            summary['skipped'] = 'rate_limited'
            return summary
        chats = (recipients or _default_recipients)()
        if not chats:
            summary['skipped'] = 'no_recipients'
            return summary
        dry = _is_dry_run()
        if dry:
            chats = chats[:1]
        deliver = _deliverer(chats, now_str, summary, send or _default_send, queue or _default_queue, dry)
        if deliver(format_review(review)):
            store.mark_notified([review_id], now_str)
            summary['marked'] = True
        return summary


def notify_pending_bot_reviews(store, now_str: Optional[str] = None, *,
                               send: Optional[Callable] = None, recipients: Optional[Callable] = None,
                               queue: Optional[Callable] = None) -> dict:
    """Подбор: отзывы из бота без отметки, добавленные за PENDING_WINDOW_HOURS.

    Помещаются в остаток часового потолка — каждый отдельным сообщением; не
    помещаются — одной сводкой (format_bot_overflow), отмечаются все. Ответ —
    {pending, sent_messages, queued_chats, marked, overflow, skipped}.
    """
    summary = {'pending': 0, 'sent_messages': 0, 'queued_chats': 0, 'marked': 0, 'overflow': 0,
               'skipped': None}
    if _switched_off(summary):
        return summary
    now_str = now_str or _now_str()
    since = _shift(now_str, -PENDING_WINDOW_HOURS * 60)
    with _notify_lock(store):
        reviews = store.all()
        pending = sorted((r for r in reviews
                          if r.get('source') == 'bot' and r.get('origin') == 'import'
                          and not r.get('tg_notified_at') and (r.get('added_at') or '') >= since),
                         key=lambda r: (r.get('created_at') or '', r.get('id') or ''))
        summary['pending'] = len(pending)
        if not pending:
            return summary
        chats = (recipients or _default_recipients)()
        if not chats:
            summary['skipped'] = 'no_recipients'
            return summary
        dry = _is_dry_run()
        if dry:
            chats = chats[:1]
        deliver = _deliverer(chats, now_str, summary, send or _default_send, queue or _default_queue, dry)
        room = max(0, NOTIFY_BOT_PER_HOUR - bot_sent_last_hour(reviews, now_str))
        marked = []
        if len(pending) <= room:
            marked = [r['id'] for r in pending if deliver(format_review(r))]
        else:
            summary['overflow'] = len(pending)
            if deliver(format_bot_overflow(len(pending))):
                marked = [r['id'] for r in pending]
        if marked:
            store.mark_notified(marked, now_str)
        summary['marked'] = len(marked)
        return summary


def notify_review_in_background(review_id: str) -> threading.Thread:
    """Для бота @kult_taplist_bot: разослать отзыв в фоновом потоке.

    Бот не ждёт Telegram владельца (два прохода с паузой при сбое связи) — гость
    сразу получает «Спасибо». Сбой пишется в лог; отзыв без отметки подберёт подбор.
    """
    def run():
        try:
            from core.guest_reviews import get_review_store
            result = notify_review_now(get_review_store(), review_id)
            print(f'[REVIEWS-BOT] уведомление об отзыве {review_id}: {result}')
        except Exception as e:  # noqa: BLE001 — фоновый поток не должен падать молча
            print(f'[REVIEWS-BOT] уведомление об отзыве {review_id} не отправлено: {e!r}')

    thread = threading.Thread(target=run, name='review-notify-' + str(review_id), daemon=True)
    thread.start()
    return thread


def notify_pending_in_background() -> Optional[threading.Thread]:
    """Для цикла опроса бота: подбор в фоновом потоке (опрос не ждёт блокировку рассылки).

    Прошлый подбор ещё идёт — новый не начинается (ответ None).
    """
    if not _sweep_guard.acquire(blocking=False):
        return None

    def run():
        try:
            from core.guest_reviews import get_review_store
            result = notify_pending_bot_reviews(get_review_store())
            if result.get('pending'):
                print(f'[REVIEWS-BOT] подбор отзывов из бота: {result}')
        except Exception as e:  # noqa: BLE001
            print(f'[REVIEWS-BOT] подбор отзывов из бота: {e!r}')
        finally:
            _sweep_guard.release()

    try:
        thread = threading.Thread(target=run, name='review-notify-sweep', daemon=True)
        thread.start()
    except Exception:
        _sweep_guard.release()
        raise
    return thread

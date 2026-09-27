"""Новые отзывы — в Telegram-бот kulturaopenclosed (бот проверки открытых смен).

Решение владельца 2026-09-28: «дублируй туда все новые отзывы». Каждый новый
отзыв из Яндекс Бизнеса после ежедневной сверки (core/yandex_reviews_sync.py)
уходит отдельным сообщением тем, кто подписался в боте кнопкой «Подписаться»
(core/open_check_subscribers.py — «подписчик получает всё»). Групповой чат
смены (TELEGRAM_GROUP_CHAT_ID) отзывы не получает: там бармены, а отзывы
бывают резкими — это решает владелец.

Что считается новым отзывом: загруженный из источника (origin 'import'),
добавленный в хранилище не раньше notify_since и ещё не отправленный
(нет tg_notified_at). notify_since — начало первой сверки с включёнными
уведомлениями (ставится один раз в состоянии сверки): 358 отзывов истории,
загруженные до этого, не рассылаются. Отметка tg_notified_at в самом отзыве —
повторная сверка и перезапуск не шлют дубль.

Отправка — тем же транспортом, что отчёты бота (open_check_bot._send_with_retries:
два прохода, обход блокировки ТСПУ); чаты, до которых не дошло, — в очередь
досылки core/open_check_pending.py (досылается до конца дня с пометкой о
задержке). Отзыв отмечается отправленным, если хоть кому-то доставлен или
поставлен в очередь.

Предохранитель: за одну сверку не больше NOTIFY_MAX_PER_RUN сообщений; если
новых больше (например, хранилище пересоздали и история загрузилась заново),
остальные — одной сводкой со ссылкой на страницу и тоже отмечаются.

Без токена бота или без подписчиков ничего не шлётся и не отмечается — отзывы
уйдут, когда появятся токен или подписчик (в пределах того же предохранителя).
OPEN_CHECK_DRY_RUN=1 — как у отчётов бота: только первому получателю, с
пометкой [DRY-RUN]. YANDEX_REVIEWS_NOTIFY=0 — не слать вовсе (проверяет
планировщик, core/yandex_reviews_scheduler.py).

Формат — HTML (parse_mode=HTML), весь текст отзыва экранируется html.escape.
Эмодзи нет (правило проекта). Документация: docs/yandex-reviews.md.
"""
import html
import os
from typing import Callable, Iterable, List, Optional

from core.guest_reviews import BARS, RATING_BUCKETS

# Предохранитель от лавины: больше — одной сводкой (см. докстринг).
NOTIFY_MAX_PER_RUN = 10
# Текст отзыва в сообщении: предел Telegram 4096 знаков на сообщение, 1500 —
# с запасом на заголовок и ответ; длиннее — обрезка с «…» и ссылка на страницу.
TEXT_PREVIEW_LEN = 1500
REPLY_PREVIEW_LEN = 300
SITE = 'https://beerkultura.ru'
SOURCE_NAMES = {'yandex': 'Яндекс Карты', 'bot': 'Бот'}
MONTHS_GEN = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
              'сентября', 'октября', 'ноября', 'декабря')
BAR_NAMES = {b['key']: b['name'] for b in BARS}


def _fmt_when(dt: Optional[str]) -> str:
    """'2026-09-27T18:30' -> '27 сентября 2026, 18:30'."""
    if not dt or len(dt) < 16:
        return ''
    y, m, d = int(dt[:4]), int(dt[5:7]), int(dt[8:10])
    return f'{d} {MONTHS_GEN[m - 1]} {y}, {dt[11:16]}'


def _cut(text: str, limit: int) -> str:
    text = (text or '').strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def candidates(reviews: Iterable[dict], since: str) -> List[dict]:
    """Новые отзывы для рассылки: загруженные, добавлены не раньше since, не отправлены.

    Порядок — по дате отзыва, затем id (детерминированно).
    """
    out = [r for r in reviews
           if r.get('origin') == 'import' and not r.get('tg_notified_at')
           and (r.get('added_at') or '') >= since]
    return sorted(out, key=lambda r: (r.get('created_at') or '', r.get('id') or ''))


def format_review(r: dict) -> str:
    """Сообщение об одном отзыве (HTML). Низкая оценка (1–2, как фильтр страницы) — в заголовке."""
    bar = BAR_NAMES.get(r.get('bar'), r.get('bar') or '')
    rating = r.get('rating')
    lo, hi = RATING_BUCKETS['low']
    low = isinstance(rating, int) and lo <= rating <= hi
    title = 'Новый отзыв — низкая оценка' if low else 'Новый отзыв'
    meta = [SOURCE_NAMES.get(r.get('source'), r.get('source') or '')]
    meta.append(f'оценка {rating} из 5' if isinstance(rating, int) else 'без оценки')
    meta.append(r.get('author') or 'без имени')
    lines = [f'<b>{html.escape(title)} · {html.escape(bar)}</b>',
             html.escape(' · '.join(meta)),
             html.escape(_fmt_when(r.get('created_at')))]
    text = _cut(r.get('text') or '', TEXT_PREVIEW_LEN)
    lines.append('')
    lines.append(f'«{html.escape(text)}»' if text else 'Текста нет — только оценка.')
    reply = r.get('reply') if isinstance(r.get('reply'), dict) else None
    lines.append('')
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
    как счётчик полосы «Требует внимания» на сайте).
    """
    items = list(reviews)
    waiting = sum(1 for r in items if r.get('status') == 'new')
    latest = sorted(items, key=lambda r: (r.get('created_at') or '', r.get('id') or ''), reverse=True)[:n]
    if not latest:
        return 'Отзывов пока нет.'
    lines = [f'<b>Последние {len(latest)} отзывов</b> · ждут ответа: {waiting}']
    for r in latest:
        rating = r.get('rating')
        head = [BAR_NAMES.get(r.get('bar'), r.get('bar') or ''),
                f'{rating} из 5' if isinstance(rating, int) else 'без оценки',
                r.get('author') or 'без имени', _fmt_when(r.get('created_at'))]
        text = _cut(r.get('text') or '', LATEST_TEXT_LEN)
        status = STATUS_WORDS.get(r.get('status'), '')
        if r.get('gone_at'):
            status += ' · нет в Яндексе'
        lines.append('')
        lines.append(f'<b>{html.escape(head[0])}</b> · ' + html.escape(' · '.join(head[1:])))
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


def _default_send(recipients: List[str], text: str) -> dict:
    from core.open_check_bot import _send_with_retries
    return _send_with_retries(recipients, text)


def _default_recipients() -> List[str]:
    from core import open_check_subscribers as subs
    return subs.get_recipients()


def _default_queue(date_str: str, text: str, chats: List[str], first_try: str) -> None:
    from core import open_check_pending
    open_check_pending.add(date_str=date_str, text=text, chats=chats, target='review', first_try=first_try)


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
    """
    since = state.setdefault('notify_since', state.get('started_at') or now_str)
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
    dry = os.environ.get('OPEN_CHECK_DRY_RUN', '').lower() in ('1', 'true', 'yes', 'on')
    if dry:
        chats = chats[:1]
    send = send or _default_send
    queue = queue or _default_queue

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

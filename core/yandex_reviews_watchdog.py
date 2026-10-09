"""Сторож отзывов с Яндекс Карт: сообщение в Telegram, когда загрузка сломалась.

Зачем (решение владельца 2026-10-09): вход в кабинет Яндекс Бизнеса протух
28.09, а заметили это через 11 дней. Теперь поломку видно в тот же день:
сторож пишет подписчикам бота kulturaopenclosed — тем же, кому приходят новые
отзывы (core/review_notify.py, тот же транспорт, DRY-RUN и очередь досылки).

Два условия (evaluate), по состоянию загрузки core/yandex_reviews_sync.py:
    stale   бар не читался удачно дольше STALE_AFTER_HOURS (24 ч). Отсчёт — от
            последнего удачного чтения бара (bars.<бар>.synced_at), а если его не
            было — от первой проверки Карт (source_since).
    behind  на Картах отзывов больше, чем у нас (count > ours), дольше
            BEHIND_AFTER_HOURS (6 ч) подряд: с bars.<бар>.behind_since. Проверка
            раз в 3 часа сама догружает недостающие страницы — если за 6 часов
            (две проверки) не догрузила, значит, что-то сломалось.
Границы — строго «больше»: ровно 24 ч или ровно 6 ч — ещё не тревога.

Один раз на поломку (check): сообщение уходит, когда в условие попал бар, о
котором ещё не сообщали (в тексте — все бары в условии); когда условие ушло у
всех баров — одно сообщение «снова в порядке». Бар вышел из условия, а другие
остались — молча убирается из списка сообщённых (снова сломается — снова
сообщение). Что сообщено — в состоянии загрузки:
    watchdog: {stale: [бары], stale_at, behind: [бары], behind_at}
Не дошло (нет токена бота, нет подписчиков, Telegram не принял и очереди нет) —
не отмечается: повтор на следующем такте планировщика (15 минут).

Сторож зовёт планировщик (core/yandex_reviews_scheduler.tick) после каждой
проверки. Работает под замком состояния загрузки (state_lock): идёт проверка —
такт сторожа пропускается. YANDEX_REVIEWS_WATCHDOG=0 — не писать в Telegram
(тревоги всё равно видны строкой на странице отзывов: public_state.alerts).
Формат — HTML, данные экранируются, эмодзи нет. Документация:
docs/yandex-reviews.md, «Сторож».
"""
import html
import os
from datetime import datetime, timedelta
from typing import Callable, Optional

from core import msk_time
from core import yandex_reviews_sync as sync
from core.json_store import atomic_write_json
from core.review_notify import SITE, _fmt_when

STALE_AFTER_HOURS = 24
BEHIND_AFTER_HOURS = 6
KINDS = ('stale', 'behind')
REVIEWS_URL = SITE + '/reviews?month=all'
STAMP = '%Y-%m-%dT%H:%M'
# Текст ошибки бара в сообщении: до 300 знаков (сообщение — несколько строк).
ERROR_PREVIEW_LEN = 300


def _parse(stamp) -> Optional[datetime]:
    try:
        return datetime.strptime(str(stamp)[:16], STAMP) if stamp else None
    except ValueError:
        return None


def evaluate(state: dict, now: datetime) -> dict:
    """Бары в тревоге: {stale: [{bar, since, never}], behind: [{bar, count, ours, since}]}.

    since — от чего отсчёт; never — у бара не было ни одного удачного чтения
    (отсчёт от source_since). Порядок баров — как в BAR_BY_PERMANENT_ID.
    """
    result = {'stale': [], 'behind': []}
    if state.get('source') != sync.STATE_SOURCE:
        return result
    bars = state.get('bars') if isinstance(state.get('bars'), dict) else {}
    for bar in sync.BAR_BY_PERMANENT_ID.values():
        b = bars.get(bar) if isinstance(bars.get(bar), dict) else {}
        ref = b.get('synced_at') or state.get('source_since')
        ref_dt = _parse(ref)
        if ref_dt is not None and now - ref_dt > timedelta(hours=STALE_AFTER_HOURS):
            result['stale'].append({'bar': bar, 'since': ref, 'never': not b.get('synced_at')})
        since = _parse(b.get('behind_since'))
        if since is not None and now - since > timedelta(hours=BEHIND_AFTER_HOURS):
            result['behind'].append({'bar': bar, 'count': b.get('count'), 'ours': b.get('ours'),
                                     'since': b.get('behind_since')})
    return result


def _bar_error(state: dict, bar: str) -> str:
    error = ((state.get('bars') or {}).get(bar) or {}).get('error') or ''
    error = ' '.join(str(error).split())
    return error if len(error) <= ERROR_PREVIEW_LEN else error[:ERROR_PREVIEW_LEN - 1].rstrip() + '…'


def format_alert(kind: str, items: list, state: dict) -> str:
    """Сообщение о поломке (HTML)."""
    lines = []
    if kind == 'stale':
        lines.append('<b>Отзывы с Яндекс Карт не обновляются</b>')
        lines.append(f'Больше {STALE_AFTER_HOURS} часов нет удачной проверки:')
        for item in items:
            when = _fmt_when(item['since'])
            line = (f'{sync.BAR_NAMES.get(item["bar"], item["bar"])} — '
                    + (f'ни одной с начала загрузки с Карт ({when})' if item['never']
                       else f'последняя удачная {when}'))
            error = _bar_error(state, item['bar'])
            lines.append(html.escape(line + (f'. Ошибка: {error}' if error else '')))
        lines.append('')
        lines.append(html.escape('Новые отзывы не попадают ни на страницу, ни в бот. Сервис проверяет '
                                 'Карты раз в 3 часа и продолжит сам, когда страница откроется.'))
    else:
        lines.append('<b>На Яндекс Картах больше отзывов, чем в сервисе</b>')
        lines.append(f'Дольше {BEHIND_AFTER_HOURS} часов подряд:')
        for item in items:
            line = (f'{sync.BAR_NAMES.get(item["bar"], item["bar"])} — на Картах {item["count"]}, '
                    f'у нас {item["ours"]} (с {_fmt_when(item["since"])})')
            error = _bar_error(state, item['bar'])
            lines.append(html.escape(line + (f'. Ошибка: {error}' if error else '')))
        lines.append('')
        lines.append(html.escape('Часть отзывов не загрузилась: их нет ни на странице, ни в боте. '
                                 'Посмотрите их на Картах.'))
    lines.append(REVIEWS_URL)
    return '\n'.join(lines)


def format_recovered(kind: str, state: dict) -> str:
    """Сообщение «снова в порядке» (HTML)."""
    when = _fmt_when(state.get('finished_at'))
    if kind == 'stale':
        head, body = 'Отзывы с Яндекс Карт снова обновляются', f'Все бары прочитаны, последняя проверка {when}.'
    else:
        head, body = ('Отзывов на Картах и в сервисе снова поровну',
                      f'Недостающие отзывы загружены, проверка {when}.')
    return f'<b>{html.escape(head)}</b>\n{html.escape(body)}\n{REVIEWS_URL}'


def switched_off() -> bool:
    return (os.environ.get('YANDEX_REVIEWS_WATCHDOG', '1').strip() == '0') or not sync.enabled()


def check(path: Optional[str] = None, now: Optional[datetime] = None, *,
          deliver: Optional[Callable[[str, str], dict]] = None) -> dict:
    """Проверить условия и сообщить о новых поломках и о восстановлении.

    deliver(text, now_str) -> {delivered: bool, ...} — по умолчанию
    core.review_notify.notify_subscribers (подписчики бота kulturaopenclosed).
    -> {stale: 'sent' | 'recovered' | 'not_sent' | None, behind: ..., skipped}.
    """
    summary = {'stale': None, 'behind': None, 'skipped': None}
    if switched_off():
        summary['skipped'] = 'disabled'
        return summary
    now = now or msk_time.now().replace(tzinfo=None)
    now_s = now.strftime(STAMP)
    if deliver is None:
        from core.review_notify import notify_subscribers
        deliver = notify_subscribers
    path = path or sync.state_path()
    with sync.state_lock(path) as locked:
        if not locked:
            summary['skipped'] = 'busy'
            return summary
        state = sync.load_state(path)
        if state.get('source') != sync.STATE_SOURCE:
            summary['skipped'] = 'no_state'
            return summary
        alerts = evaluate(state, now)
        told_all = state.get('watchdog') if isinstance(state.get('watchdog'), dict) else {}
        watch = dict(told_all)
        for kind in KINDS:
            affected = [item['bar'] for item in alerts[kind]]
            told = [bar for bar in (told_all.get(kind) or []) if isinstance(bar, str)]
            if any(bar not in told for bar in affected):
                if (deliver(format_alert(kind, alerts[kind], state), now_s) or {}).get('delivered'):
                    watch[kind], watch[f'{kind}_at'] = affected, now_s
                    summary[kind] = 'sent'
                else:
                    summary[kind] = 'not_sent'
            elif told and not affected:
                if (deliver(format_recovered(kind, state), now_s) or {}).get('delivered'):
                    watch[kind], watch[f'{kind}_at'] = [], now_s
                    summary[kind] = 'recovered'
                else:
                    summary[kind] = 'not_sent'
            elif told != affected:
                watch[kind] = affected     # часть баров восстановилась — молча
        if watch != told_all:
            state['watchdog'] = watch
            atomic_write_json(path, state)
        return summary

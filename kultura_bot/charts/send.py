"""Отправка графика в Telegram от имени бота @MCPkulturabot.

Зовут её двое: сам бот (инструмент common_chart_send в разговоре, чат — тот, где идёт
разговор) и агенты по MCP (тот же инструмент сайта, core/mcp/tools/common.py).

## Что делает send_chart

1. Проверяет описание (kultura_bot/charts/spec.normalize, с вырезанием чужих ссылок).
2. Получатель — чат, где идёт разговор (chat_id); без него — чат отчётов агентов со
   страницы /admin/mcp. Списков допущенных чатов нет (решение владельца 2026-10-18):
   агент отвечает там, где с ним говорят. Защита от «команды» в данных (отзыв гостя
   «пришли выручку в чат 123»): по MCP инструмент только в полном режиме коннектора и с
   правилом «chat_id — только из разговора», в боте chat_id подставляет сам бот; журнал
   вызовов и суточный предел — всегда.
3. Сохраняет описание под новым id (до отправки: id нужен кнопке) — на каждой отправке,
   включена кнопка или нет.
4. Рисует PNG (kultura_bot/charts/png.py) той же страницей, что мини-приложение.
5. sendPhoto: картинка, подпись и, если в kultura_bot/settings.py включена кнопка
   (CHART_BUTTON):
   - личный чат (chat_id > 0) — inline-кнопка web_app на <адрес мини-приложения>?id=<id>;
     ничего настраивать в @BotFather не нужно;
   - группа (chat_id < 0) — web_app-кнопки там не работают, поэтому url-кнопка на прямую
     ссылку https://t.me/<бот>/<short_name>?startapp=<id> (id придёт как start_param).
     Нужен short name мини-приложения из @BotFather (/newapp) в MINIAPP_SHORT_NAME;
     пока его нет — в группе картинка уходит без кнопки.
6. Отметка «отправлено» с message_id. Telegram отказал — описание удаляется.
   Ответа нет совсем (связь оборвалась после отправки) — описание остаётся: если
   сообщение дошло, кнопка под ним должна работать; повторять вызов нельзя.

## Подпись — это ответ (решение владельца 2026-10-24, «один пузырь»)

caption — Markdown бота (как текст ответа: **жирный**, пункты, цитаты «> »): сайт
переводит его в HTML Telegram (kultura_bot/engine/formatting.to_html — тот же перевод, что
у сообщений бота) и шлёт с parse_mode=HTML; переводы строк сохраняются. Предел Telegram —
1024 знака видимого текста (без тегов). Telegram не разобрал разметку — та же подпись
уходит простым текстом.

how — «Как считается» к этому ответу (Markdown): сохраняется запиской (charts/reports.py)
и не занимает места в подписи: ссылка «Как считается» в конце подписи (есть короткое
имя мини-приложения) или кнопка рядом с «Открыть интерактивно» (личка) — kultura_bot/links.py.

## Отчёт (send_report)

Большой ответ — страница отчёта (charts/reports.py): сайт сохраняет отчёт, в чат уходит
выжимка (summary) — подписью к обложке (первый график отчёта, PNG) или сообщением, если
графиков нет, — и кнопка «Открыть отчёт»: личка — мини-приложение, группа — прямая
ссылка t.me (короткое имя) или страница сайта /tg/report/<id> (вход сайта).

Токен бота — kultura_bot/credentials.py (страница /admin/mcp); кнопка, short name, адрес
мини-приложения и суточный предел — kultura_bot/settings.py. Готовность для агента (блок
charts в common_whoami: есть ли токен и кнопка, что сделать владельцу) — readiness().
"""
import json
import logging
import re
from typing import Any, Callable, Dict, Optional

from kultura_bot import credentials, links, settings
from kultura_bot.charts import reports, spec as chart_spec

log = logging.getLogger('tg-charts')

BUTTON_TEXT = links.CHART_TEXT
CAPTION_MAX = 1024          # предел подписи к фото в Telegram Bot API (видимый текст, без тегов)
MESSAGE_MAX = 4096          # предел текста сообщения
CAPTION_SOURCE_MAX = 4000   # Markdown подписи до перевода в HTML

_CHAT_ID_RE = re.compile(r'-?\d{1,20}')

TextFilter = Callable[[str], str]


class ChartSendError(Exception):
    """Отправка не состоялась (или настройка не сделана): текст — для агента."""


def notify_chat_id() -> str:
    """Чат отчётов агентов со страницы «Доступ агентов» (/admin/mcp) — по умолчанию сюда."""
    try:
        from core.mcp import settings as mcp_settings
        return str(mcp_settings.get('notify_chat_id') or '').strip()
    except Exception:  # noqa: BLE001 — нет настроек, значит нет чата по умолчанию
        return ''


def _section() -> str:
    return f'раздел «Бот @{credentials.bot_username()}»'


def readiness() -> Dict[str, Any]:
    """Готовность графиков для агента (common_whoami), без токена.

    Агент видит это в начале каждого разговора: слать графики через сервис и что
    сказать владельцу, если не хватает настройки (owner_todo; пусто — всё готово).
    """
    configured = bool(credentials.bot_token())
    button = configured and settings.CHART_BUTTON
    if not configured:
        todo = (f'вставить токен бота @{credentials.bot_username()} на странице {settings.ADMIN_PAGE_URL}, '
                f'{_section()}, и нажать «Сохранить»')
    elif not button:
        todo = 'включить кнопку «Открыть интерактивно»: CHART_BUTTON в kultura_bot/settings.py'
    else:
        todo = ''
    return {'tool': 'common_chart_send', 'ready': configured, 'button': button, 'owner_todo': todo}


def chart_button(chat_id: str, chart_id: str) -> Optional[Dict[str, Any]]:
    """Кнопка «Открыть интерактивно» или None (выключена; в группе — нет short name)."""
    if not settings.CHART_BUTTON:
        return None
    return links.button(BUTTON_TEXT, chat_id, chart_id, credentials.bot_username())


def button_markup(chat_id: str, chart_id: str) -> Optional[Dict[str, Any]]:
    """inline_keyboard под картинкой или None (кнопка выключена; в группе — нет short name)."""
    button = chart_button(chat_id, chart_id)
    return {'inline_keyboard': [[button]]} if button else None


def _caption_markdown(caption: Any, where: str = 'caption') -> str:
    """Markdown подписи: строки сохраняются, лишние пробелы по краям строк и пустые строки — нет."""
    if caption is None:
        return ''
    if not isinstance(caption, str):
        raise ChartSendError(f'{where}: нужна строка')
    lines = [' '.join(line.split()) for line in caption.replace('\r', '').split('\n')]
    text = '\n'.join(lines).strip('\n')
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    if len(text) > CAPTION_SOURCE_MAX:
        raise ChartSendError(f'{where}: длиннее {CAPTION_SOURCE_MAX} символов')
    return text


def _html(markdown: str) -> str:
    from kultura_bot.engine import formatting
    return formatting.to_html(markdown)


def _visible_len(text_html: str) -> int:
    from kultura_bot.engine import formatting
    return formatting.visible_len(text_html)


def _plain(markdown: str) -> str:
    from kultura_bot.engine import formatting
    return formatting.plain(markdown)


def _with_link(markdown: str, text: str, url: str) -> str:
    from kultura_bot.engine import formatting
    return formatting.with_link(markdown, text, url)


def _save_note(how: Any, *, chat: str, token_id: str, page_filter: Optional[TextFilter]) -> Optional[str]:
    """Записка «Как считается» к ответу (или None, если how пуст). Ошибка — ChartSendError."""
    if how in (None, '') or (isinstance(how, str) and not how.strip()):
        return None
    try:
        body = reports.normalize_note(how, page_filter=page_filter)
        return reports.create(body, chat_id=chat, token_id=token_id,
                              daily_limit=settings.REPORT_DAILY_LIMIT)['id']
    except reports.ReportError as exc:
        raise ChartSendError(f'how: {exc}') from None
    except reports.ReportLimitError as exc:
        raise ChartSendError(f'Лимит: не больше {settings.REPORT_DAILY_LIMIT} записок и отчётов в сутки — '
                             f'сегодня уже {exc.used}.') from None


def _chat(chat_id: Any) -> str:
    chat = str(chat_id).strip() if chat_id not in (None, '') else notify_chat_id()
    if not chat:
        raise ChartSendError('Не указан chat_id, и чат отчётов агентов не выбран на странице «Доступ агентов».')
    if not _CHAT_ID_RE.fullmatch(chat):
        raise ChartSendError('chat_id — целое число (у групп со знаком минус), например 670033096')
    return chat


def _token() -> str:
    token = credentials.bot_token()
    if not token:
        raise ChartSendError('Не настроено: нет токена бота графиков. Скажи владельцу дословно: «Чтобы графики '
                             'приходили с кнопкой «Открыть интерактивно», вставьте токен бота '
                             f'@{credentials.bot_username()} на странице «Доступ агентов» '
                             f'({settings.ADMIN_PAGE_URL}), {_section()}, и нажмите «Сохранить»».')
    return token


def _parse_failed(data: Optional[Dict[str, Any]]) -> bool:
    """Telegram не разобрал разметку (сообщение не ушло — можно слать простым текстом)."""
    return bool(data) and not data.get('ok') and 'parse' in str(data.get('description') or '').lower()


def _transport(fields: Dict[str, str], png: bytes, token: str, outcome: list):
    """sendPhoto тем же путём с обходом блокировок, что посты каналов (тесты подменяют)."""
    from core.open_check_telegram import api_call_files
    return api_call_files('sendPhoto', fields, [('photo', 'chart.png', png, 'image/png')], token=token,
                          safe_resend=True, outcome=outcome)


def _transport_message(payload: Dict[str, Any], token: str, outcome: list):
    """sendMessage тем же путём (выжимка отчёта без графика; тесты подменяют)."""
    from core.open_check_telegram import api_call
    return api_call('sendMessage', payload, timeout=20, token=token, safe_resend=True, outcome=outcome)


def _render(spec: Dict[str, Any]) -> bytes:
    from kultura_bot.charts import png
    return png.render_png(spec)


def send_chart(raw_spec: Any, *, chat_id: Any = None, caption: Optional[str] = None, how: Optional[str] = None,
               token_id: str = '', text_filter: Optional[TextFilter] = None,
               page_filter: Optional[TextFilter] = None) -> Dict[str, Any]:
    """Нарисовать и отправить график. Вернуть {chart_id, chat_id, message_id, button, ...}.

    caption — ответ (Markdown бота), how — «Как считается» (Markdown, уходит запиской).
    text_filter — над тем, что уходит в Telegram; page_filter — над текстом записки.
    Ошибка настройки, проверки или отправки — ChartSendError с понятным текстом.
    """
    token = _token()
    chat = _chat(chat_id)
    try:
        spec = chart_spec.normalize(raw_spec, text_filter=text_filter)
    except chart_spec.ChartSpecError as exc:
        raise ChartSendError(f'Описание графика: {exc}') from None
    text = _caption_markdown(caption)
    if text_filter is not None and text:
        text = text_filter(text)
    text = text or spec['title']
    if _visible_len(_html(text)) > CAPTION_MAX:
        raise ChartSendError(f'caption длиннее {CAPTION_MAX} знаков без разметки ({_visible_len(_html(text))}): '
                             'сократи подпись — пояснение расчёта передай в how, оно не занимает места')

    limit = settings.CHART_DAILY_LIMIT
    try:
        record = chart_spec.create(spec, chat_id=chat, token_id=token_id, daily_limit=limit)
    except chart_spec.ChartLimitError as exc:
        raise ChartSendError(f'Лимит: не больше {limit} графиков в сутки — сегодня уже {exc.used}.') from None
    chart_id = record['id']
    try:
        how_id = _save_note(how, chat=chat, token_id=token_id, page_filter=page_filter)
    except ChartSendError:
        chart_spec.delete(chart_id)
        raise

    def forget():
        chart_spec.delete(chart_id)
        if how_id:
            reports.delete(how_id)

    row = []
    chart_btn = chart_button(chat, chart_id)
    if chart_btn:
        row.append(chart_btn)
    how_kind = None
    if how_id:
        target = links.how_target(chat, how_id, credentials.bot_username())
        if 'link' in target:
            linked = _with_link(text, links.HOW_TEXT, target['link'])
            if _visible_len(_html(linked)) <= CAPTION_MAX:
                text, how_kind = linked, 'link'
        if how_kind is None and 'button' in target:
            row.append(target['button'])
            how_kind = 'button'
        if how_kind is None:
            # ссылка не влезла в подпись (впритык к пределу): кнопкой, если можно
            fallback = links.button(links.HOW_TEXT, chat, how_id, credentials.bot_username(), site_fallback=True)
            if fallback:
                row.append(fallback)
                how_kind = 'button'
    try:
        png = _render(spec)
    except Exception as exc:  # noqa: BLE001 — картинки нет, значит и описание не нужно
        forget()
        log.warning('[TG-CHART] картинка не нарисована: %s: %s', type(exc).__name__, exc)
        raise ChartSendError(f'Картинка не нарисована: {type(exc).__name__}: {exc}') from None

    fields = {'chat_id': chat, 'caption': _html(text), 'parse_mode': 'HTML'}
    markup = {'inline_keyboard': [row]} if row else None
    if markup is not None:
        fields['reply_markup'] = json.dumps(markup, ensure_ascii=False)
    outcome: list = []
    data = _transport(fields, png, token, outcome)
    if _parse_failed(data):
        fields.pop('parse_mode')
        fields['caption'] = _plain(text)[:CAPTION_MAX]
        outcome = []
        data = _transport(fields, png, token, outcome)
    if data is None and 'unknown' in outcome:
        # Запрос ушёл, ответа нет: сообщение могло дойти — описание оставляем для кнопки.
        raise ChartSendError(f'Статус неизвестен: Telegram не ответил, сообщение могло дойти. Не повторяйте '
                             f'отправку, пока владелец не проверит чат (график {chart_id}).')
    if not data or not data.get('ok'):
        forget()
        reason = (data or {}).get('description') or 'нет связи с Telegram'
        raise ChartSendError(f'Telegram не принял картинку: {reason}')
    message_id = (data.get('result') or {}).get('message_id')
    chart_spec.mark_sent(chart_id, message_id)
    if how_id:
        reports.mark_sent(how_id, message_id)
    result = {
        'chart_id': chart_id,
        'chat_id': chat,
        'message_id': message_id,
        'button': ('url' if chat.startswith('-') else 'web_app') if chart_btn is not None else None,
        'expires_at': record['expires_at'],
        'sent_today': record['used_today'],
        'daily_limit': limit,
    }
    if how_id:
        result['how'] = {'id': how_id, 'shown_as': how_kind}
    if chart_btn is None and settings.CHART_BUTTON and chat.startswith('-'):
        result['button_note'] = ('в группе кнопки нет: не задано короткое имя мини-приложения (@BotFather → '
                                 '/newapp) — его вписывают в MINIAPP_SHORT_NAME в kultura_bot/settings.py')
    return result


def send_report(raw_report: Any, *, chat_id: Any = None, token_id: str = '',
                text_filter: Optional[TextFilter] = None,
                page_filter: Optional[TextFilter] = None) -> Dict[str, Any]:
    """Сохранить отчёт и отправить в чат выжимку с кнопкой «Открыть отчёт».

    Обложка — первый график отчёта (фото, выжимка — подписью, предел 1024 знака); графиков
    нет — сообщение (предел 4096). Вернуть {report_id, chat_id, message_id, url, ...}.
    Ошибка — ChartSendError с понятным текстом."""
    token = _token()
    chat = _chat(chat_id)
    try:
        body = reports.normalize_report(raw_report, text_filter=text_filter, page_filter=page_filter)
    except reports.ReportError as exc:
        raise ChartSendError(f'Отчёт: {exc}') from None
    cover = reports.cover_chart(body)
    summary_html = _html(body['summary'])
    limit = CAPTION_MAX if cover else MESSAGE_MAX
    visible = _visible_len(summary_html)
    if visible > limit:
        where = 'подпись к обложке (первому графику)' if cover else 'сообщение'
        raise ChartSendError(f'summary длиннее {limit} знаков без разметки ({visible}): это {where} в чате — '
                             'оставь лид и 2–4 строки, подробности уже на странице отчёта')
    try:
        record = reports.create(body, chat_id=chat, token_id=token_id, daily_limit=settings.REPORT_DAILY_LIMIT)
    except reports.ReportLimitError as exc:
        raise ChartSendError(f'Лимит: не больше {settings.REPORT_DAILY_LIMIT} записок и отчётов в сутки — '
                             f'сегодня уже {exc.used}.') from None
    report_id = record['id']
    button = links.button(links.REPORT_TEXT, chat, report_id, credentials.bot_username(), site_fallback=True)
    markup = {'inline_keyboard': [[button]]} if button else None
    outcome: list = []
    if cover:
        try:
            png = _render(cover)
        except Exception as exc:  # noqa: BLE001 — обложки нет, значит и отчёт не уходит
            reports.delete(report_id)
            log.warning('[TG-REPORT] обложка не нарисована: %s: %s', type(exc).__name__, exc)
            raise ChartSendError(f'Обложка отчёта не нарисована: {type(exc).__name__}: {exc}') from None
        fields = {'chat_id': chat, 'caption': summary_html, 'parse_mode': 'HTML'}
        if markup:
            fields['reply_markup'] = json.dumps(markup, ensure_ascii=False)
        data = _transport(fields, png, token, outcome)
        if _parse_failed(data):
            fields.pop('parse_mode')
            fields['caption'] = _plain(body['summary'])[:CAPTION_MAX]
            outcome = []
            data = _transport(fields, png, token, outcome)
    else:
        payload: Dict[str, Any] = {'chat_id': chat, 'text': summary_html, 'parse_mode': 'HTML',
                                   'link_preview_options': {'is_disabled': True}}
        if markup:
            payload['reply_markup'] = markup
        data = _transport_message(payload, token, outcome)
        if _parse_failed(data):
            payload.pop('parse_mode')
            payload['text'] = _plain(body['summary'])[:MESSAGE_MAX]
            outcome = []
            data = _transport_message(payload, token, outcome)
    if data is None and 'unknown' in outcome:
        raise ChartSendError(f'Статус неизвестен: Telegram не ответил, сообщение могло дойти. Не повторяйте '
                             f'отправку, пока владелец не проверит чат (отчёт {report_id}).')
    if not data or not data.get('ok'):
        reports.delete(report_id)
        reason = (data or {}).get('description') or 'нет связи с Telegram'
        raise ChartSendError(f'Telegram не принял отчёт: {reason}')
    message_id = (data.get('result') or {}).get('message_id')
    reports.mark_sent(report_id, message_id)
    return {
        'report_id': report_id,
        'chat_id': chat,
        'message_id': message_id,
        'cover': bool(cover),
        'button': ('url' if 'url' in button else 'web_app') if button else None,
        'url': links.site_page(report_id),
        'sections': len(body['sections']),
        'expires_at': record['expires_at'],
    }

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

Токен бота — kultura_bot/credentials.py (страница /admin/mcp); кнопка, short name, адрес
мини-приложения и суточный предел — kultura_bot/settings.py. Готовность для агента (блок
charts в common_whoami: есть ли токен и кнопка, что сделать владельцу) — readiness().
"""
import json
import logging
import re
from typing import Any, Callable, Dict, Optional

from kultura_bot import credentials, settings
from kultura_bot.charts import spec as chart_spec

log = logging.getLogger('tg-charts')

BUTTON_TEXT = 'Открыть интерактивно'
CAPTION_MAX = 1024          # предел подписи к фото в Telegram Bot API

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


def button_markup(chat_id: str, chart_id: str) -> Optional[Dict[str, Any]]:
    """inline_keyboard под картинкой или None (кнопка выключена; в группе — нет short name)."""
    if not settings.CHART_BUTTON:
        return None
    if str(chat_id).startswith('-'):
        short = (settings.MINIAPP_SHORT_NAME or '').strip()
        if not short:
            return None
        button = {'text': BUTTON_TEXT,
                  'url': f'https://t.me/{credentials.bot_username()}/{short}?startapp={chart_id}'}
    else:
        button = {'text': BUTTON_TEXT, 'web_app': {'url': f'{settings.MINIAPP_URL}?id={chart_id}'}}
    return {'inline_keyboard': [[button]]}


def _transport(fields: Dict[str, str], png: bytes, token: str, outcome: list):
    """sendPhoto тем же путём с обходом блокировок, что посты каналов (тесты подменяют)."""
    from core.open_check_telegram import api_call_files
    return api_call_files('sendPhoto', fields, [('photo', 'chart.png', png, 'image/png')], token=token,
                          safe_resend=True, outcome=outcome)


def _render(spec: Dict[str, Any]) -> bytes:
    from kultura_bot.charts import png
    return png.render_png(spec)


def send_chart(raw_spec: Any, *, chat_id: Any = None, caption: Optional[str] = None, token_id: str = '',
               text_filter: Optional[TextFilter] = None) -> Dict[str, Any]:
    """Нарисовать и отправить график. Вернуть {chart_id, chat_id, message_id, button, ...}.

    Ошибка настройки, проверки или отправки — ChartSendError с понятным текстом.
    """
    token = credentials.bot_token()
    if not token:
        raise ChartSendError('Не настроено: нет токена бота графиков. Скажи владельцу дословно: «Чтобы графики '
                             'приходили с кнопкой «Открыть интерактивно», вставьте токен бота '
                             f'@{credentials.bot_username()} на странице «Доступ агентов» '
                             f'({settings.ADMIN_PAGE_URL}), {_section()}, и нажмите «Сохранить»».')
    chat = str(chat_id).strip() if chat_id not in (None, '') else notify_chat_id()
    if not chat:
        raise ChartSendError('Не указан chat_id, и чат отчётов агентов не выбран на странице «Доступ агентов».')
    if not _CHAT_ID_RE.fullmatch(chat):
        raise ChartSendError('chat_id — целое число (у групп со знаком минус), например 670033096')
    try:
        spec = chart_spec.normalize(raw_spec, text_filter=text_filter)
    except chart_spec.ChartSpecError as exc:
        raise ChartSendError(f'Описание графика: {exc}') from None
    text = ' '.join((caption if isinstance(caption, str) else '').split())
    if text_filter is not None and text:
        text = text_filter(text)
    text = text or spec['title']
    if len(text) > CAPTION_MAX:
        raise ChartSendError(f'caption длиннее {CAPTION_MAX} символов')

    limit = settings.CHART_DAILY_LIMIT
    try:
        record = chart_spec.create(spec, chat_id=chat, token_id=token_id, daily_limit=limit)
    except chart_spec.ChartLimitError as exc:
        raise ChartSendError(f'Лимит: не больше {limit} графиков в сутки — сегодня уже {exc.used}.') from None
    chart_id = record['id']
    try:
        png = _render(spec)
    except Exception as exc:  # noqa: BLE001 — картинки нет, значит и описание не нужно
        chart_spec.delete(chart_id)
        log.warning('[TG-CHART] картинка не нарисована: %s: %s', type(exc).__name__, exc)
        raise ChartSendError(f'Картинка не нарисована: {type(exc).__name__}: {exc}') from None

    fields = {'chat_id': chat, 'caption': text}
    markup = button_markup(chat, chart_id)
    if markup is not None:
        fields['reply_markup'] = json.dumps(markup, ensure_ascii=False)
    outcome: list = []
    data = _transport(fields, png, token, outcome)
    if data is None and 'unknown' in outcome:
        # Запрос ушёл, ответа нет: сообщение могло дойти — описание оставляем для кнопки.
        raise ChartSendError(f'Статус неизвестен: Telegram не ответил, сообщение могло дойти. Не повторяйте '
                             f'отправку, пока владелец не проверит чат (график {chart_id}).')
    if not data or not data.get('ok'):
        chart_spec.delete(chart_id)
        reason = (data or {}).get('description') or 'нет связи с Telegram'
        raise ChartSendError(f'Telegram не принял картинку: {reason}')
    message_id = (data.get('result') or {}).get('message_id')
    chart_spec.mark_sent(chart_id, message_id)
    result = {
        'chart_id': chart_id,
        'chat_id': chat,
        'message_id': message_id,
        'button': ('url' if chat.startswith('-') else 'web_app') if markup is not None else None,
        'expires_at': record['expires_at'],
        'sent_today': record['used_today'],
        'daily_limit': limit,
    }
    if markup is None and settings.CHART_BUTTON and chat.startswith('-'):
        result['button_note'] = ('в группе кнопки нет: не задано короткое имя мини-приложения (@BotFather → '
                                 '/newapp) — его вписывают в MINIAPP_SHORT_NAME в kultura_bot/settings.py')
    return result

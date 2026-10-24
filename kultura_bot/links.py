"""Куда ведут кнопки и ссылки под ответами бота: мини-приложение и страница сайта.

Общий модуль сайта (kultura_bot/charts/send.py — графики и отчёты) и сервера бота
(kultura_bot/engine/service.py — «Как считается» под текстовым ответом). Кода сайта не
импортирует: на сервере бота в Амстердаме его нет.

## Что открывается

Запись по id: график (tg_charts, id — 22 знака token_urlsafe), отчёт или записка «Как
считается» (tg_reports, id — REPORT_ID_RE: «rep_» и 22 шестнадцатеричных знака).
Мини-приложение одно (/tg/chart): по виду id само решает, что загрузить.

## Как открывается (решение владельца 2026-10-24: «Как считается» — за ссылкой)

- задано короткое имя мини-приложения (settings.MINIAPP_SHORT_NAME, @BotFather /newapp) —
  прямая ссылка https://t.me/<бот>/<имя>?startapp=<id>: работает в личке и в группе,
  открывает мини-приложение внутри Telegram. Её можно поставить текстом в конец ответа —
  ни строки места;
- имени нет, личный чат — кнопка web_app (<MINIAPP_URL>?id=<id>): настраивать ничего не
  нужно, но кнопка — это ряд под сообщением;
- имени нет, группа — web_app-кнопки там запрещены Telegram: ссылка на страницу сайта
  /tg/report/<id> (обычный вход сайта; у бота и так только администраторы сайта). Для
  графиков такой страницы нет — в группе без имени график уходит без кнопки.
"""
import re
from typing import Any, Dict, Optional

from kultura_bot import settings

REPORT_ID_RE = re.compile(r'rep_[0-9a-f]{22}')
HOW_TEXT = 'Как считается'
REPORT_TEXT = 'Открыть отчёт'
CHART_TEXT = 'Открыть интерактивно'


def is_group(chat_id: Any) -> bool:
    return str(chat_id or '').strip().startswith('-')


def miniapp_url(item_id: str) -> str:
    """Адрес мини-приложения для кнопки web_app (только личка)."""
    return f'{settings.MINIAPP_URL}?id={item_id}'


def direct_link(bot_username: str, item_id: str) -> str:
    """Прямая ссылка на мини-приложение (t.me/<бот>/<имя>?startapp=<id>) или '' без короткого имени."""
    short = (settings.MINIAPP_SHORT_NAME or '').strip()
    bot = (bot_username or settings.BOT_USERNAME or '').lstrip('@')
    if not short or not bot:
        return ''
    return f'https://t.me/{bot}/{short}?startapp={item_id}'


def site_page(report_id: str) -> str:
    """Страница отчёта или записки на сайте (нужен вход в сайт)."""
    return f'{settings.SITE_URL}/tg/report/{report_id}'


def button(text: str, chat_id: Any, item_id: str, bot_username: str, *,
           site_fallback: bool = False) -> Optional[Dict[str, Any]]:
    """Кнопка inline-клавиатуры или None (группа без короткого имени и без запасной страницы).

    site_fallback — в группе без короткого имени вести на страницу сайта (есть у отчётов и
    записок, у графиков нет)."""
    if not is_group(chat_id):
        return {'text': text, 'web_app': {'url': miniapp_url(item_id)}}
    link = direct_link(bot_username, item_id)
    if link:
        return {'text': text, 'url': link}
    if site_fallback:
        return {'text': text, 'url': site_page(item_id)}
    return None


def how_target(chat_id: Any, note_id: str, bot_username: str) -> Dict[str, Any]:
    """Куда ведёт «Как считается»: {'link': url} — текстом в конце ответа, или
    {'button': {...}} — кнопкой под ним (личка без короткого имени)."""
    link = direct_link(bot_username, note_id)
    if link:
        return {'link': link}
    if not is_group(chat_id):
        return {'button': {'text': HOW_TEXT, 'web_app': {'url': miniapp_url(note_id)}}}
    return {'link': site_page(note_id)}

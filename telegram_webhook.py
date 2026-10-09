"""
Telegram бот для KULT Taplist - Webhook версия
Работает внутри Flask приложения без отдельного процесса.

Основной режим — long-polling (core/taplist_polling.py): входящие от Telegram до
сервера не доходят. Таплист в обоих режимах один: реестр Untappd (связь по GUID
товара iiko) и строки «Таплиста пятницы» — core/taplist_post.bar_message_html.
Прежний справочник по названиям (beer_info_mapping.json) с 2026-10-04 не читается.
"""
import os
import json
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from aiogram.client.session.aiohttp import AiohttpSession

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация. Токен ТОЛЬКО из env — никаких хардкод-fallback'ов
# (раньше тут был реальный токен в коде, что утекало в git).
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN не задан. Установите переменную окружения "
        "перед запуском (или уберите импорт telegram_webhook из extensions.py)."
    )

# Конфигурация баров
BARS_CONFIG = {
    'bar1': 'Большой пр. В.О',
    'bar2': 'Лиговский',
    'bar3': 'Кременчугская',
    'bar4': 'Варшавская',
}

# Инициализация бота (без polling).
# Явный таймаут сессии (15с вместо дефолтных 60): обработка webhook идёт внутри
# Flask-воркера, а их всего 2 — медленный Telegram не должен надолго занять воркер.
bot = Bot(token=BOT_TOKEN, session=AiohttpSession(timeout=15))
dp = Dispatcher()


TAPLIST_ERROR_TEXT = 'Не удалось получить данные о кранах. Попробуйте позже.'


def taplist_messages(bar_id=None, taps_manager=None):
    """Таплист по сообщению на бар (HTML): реестр Untappd, строки «Таплиста пятницы».

    bar_id None — все бары по порядку. Сбой данных бара — текст извинения вместо
    его сообщения: остальные бары всё равно уходят."""
    from core import taplist_post
    manager = taps_manager or _taps_manager
    if manager is None:
        return [TAPLIST_ERROR_TEXT]
    messages = []
    for b_id in ([bar_id] if bar_id else list(BARS_CONFIG)):
        try:
            messages.append(taplist_post.bar_message_html(manager, b_id, BARS_CONFIG.get(b_id, b_id)))
        except Exception as e:  # noqa: BLE001 — один бар не должен ломать ответ
            logger.error(f"Taplist for {b_id} failed: {e!r}")
            messages.append(TAPLIST_ERROR_TEXT)
    return messages


def get_bars_keyboard():
    """Создать клавиатуру выбора бара"""
    buttons = []
    for bar_id, bar_name in BARS_CONFIG.items():
        buttons.append([InlineKeyboardButton(text=f"🍺 {bar_name}", callback_data=f"taplist_{bar_id}")])
    buttons.append([InlineKeyboardButton(text="📋 Все бары", callback_data="taplist_all")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Handlers
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    await message.answer(
        "🍺 <b>KULT Taplist Bot</b>\n\n"
        "Узнай что сейчас на кранах!\n\n"
        "<b>Команды:</b>\n"
        "/taplist — выбрать бар\n"
        "/taplist1 — Большой пр. В.О\n"
        "/taplist2 — Лиговский\n"
        "/taplist3 — Кременчугская\n"
        "/taplist4 — Варшавская\n"
        "/taplistall — все бары\n"
        "/help — помощь",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    await message.answer(
        "<b>Доступные команды:</b>\n\n"
        "/taplist — меню выбора бара\n"
        "/taplist1 — Большой пр. В.О\n"
        "/taplist2 — Лиговский\n"
        "/taplist3 — Кременчугская\n"
        "/taplist4 — Варшавская\n"
        "/taplistall — все бары\n\n"
        "<i>Название — ссылка на Untappd, дальше стиль и крепость; новые сорта помечены «новинка»</i>",
        parse_mode="HTML"
    )


@dp.message(Command("taplist"))
async def cmd_taplist(message: types.Message):
    """Команда /taplist — показать выбор бара"""
    await message.answer(
        "🍺 Выберите бар:",
        reply_markup=get_bars_keyboard()
    )


# Глобальные переменные для доступа к данным (будут установлены из app.py)
_taps_manager = None


def set_data_sources(taps_manager):
    """Установить менеджер кранов из Flask приложения (данные о пиве — реестр Untappd)."""
    global _taps_manager
    _taps_manager = taps_manager
    logger.info("Data sources set for Telegram bot")


async def send_taplist_response(message: types.Message, bar_id=None):
    """Отправить таплист: по сообщению на бар."""
    for text in taplist_messages(bar_id):
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@dp.message(Command("taplist1"))
async def cmd_taplist1(message: types.Message):
    await send_taplist_response(message, 'bar1')


@dp.message(Command("taplist2"))
async def cmd_taplist2(message: types.Message):
    await send_taplist_response(message, 'bar2')


@dp.message(Command("taplist3"))
async def cmd_taplist3(message: types.Message):
    await send_taplist_response(message, 'bar3')


@dp.message(Command("taplist4"))
async def cmd_taplist4(message: types.Message):
    await send_taplist_response(message, 'bar4')


@dp.message(Command("taplistall"))
async def cmd_taplist_all(message: types.Message):
    await send_taplist_response(message, None)


@dp.callback_query(lambda c: c.data.startswith('taplist_'))
async def process_taplist_callback(callback: types.CallbackQuery):
    """Обработка выбора бара"""
    bar_id = callback.data.replace('taplist_', '')

    await callback.answer("Загрузка...")

    for text in taplist_messages(None if bar_id == 'all' else bar_id):
        await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


async def process_telegram_update(update_data: dict):
    """
    Обработать входящий webhook update от Telegram
    Вызывается из Flask endpoint
    """
    try:
        update = Update.model_validate(update_data)
        await dp.feed_update(bot, update)
        return True
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return False


async def set_webhook(webhook_url: str):
    """Установить webhook URL"""
    try:
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True
        )
        logger.info(f"Webhook set to: {webhook_url}")
        return True
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return False


async def delete_webhook():
    """Удалить webhook (для переключения на polling)"""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted")
        return True
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
        return False


async def get_webhook_info():
    """Получить информацию о текущем webhook"""
    try:
        info = await bot.get_webhook_info()
        return {
            'url': info.url,
            'has_custom_certificate': info.has_custom_certificate,
            'pending_update_count': info.pending_update_count,
            'last_error_date': info.last_error_date,
            'last_error_message': info.last_error_message
        }
    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        return None

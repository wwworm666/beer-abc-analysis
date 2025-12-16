"""
Telegram бот для получения таплиста KULT
Получает данные через API с Render
"""
import asyncio
import os
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8261982160:AAFu1YfpSQBB1lRC_gDxobwBfSL5kI0UKK8')
API_BASE_URL = os.getenv('API_BASE_URL', 'https://beer-abc-analysis.onrender.com')

# Конфигурация баров
BARS_CONFIG = {
    'bar1': 'Большой пр. В.О',
    'bar2': 'Лиговский',
    'bar3': 'Кременчугская',
    'bar4': 'Варшавская',
}

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def fetch_taplist(bar_id: str = None) -> dict:
    """Получить таплист через API"""
    url = f"{API_BASE_URL}/api/taps/taplist-full"
    params = {'active_only': 'true'}
    if bar_id:
        params['bar_id'] = bar_id

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API error: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching taplist: {e}")
        return None


def format_taplist_message(data: dict, bar_id: str = None) -> str:
    """Форматировать таплист для Telegram"""
    if not data or not data.get('success'):
        return "Не удалось получить данные о кранах. Попробуйте позже."

    taplist = data.get('taplist', [])
    if not taplist:
        return "Нет активных кранов"

    # Группируем по барам
    bars_data = {}
    for tap in taplist:
        b_id = tap.get('bar_id', 'unknown')
        if b_id not in bars_data:
            bars_data[b_id] = {
                'name': tap.get('bar', BARS_CONFIG.get(b_id, b_id)),
                'taps': []
            }
        bars_data[b_id]['taps'].append(tap)

    # Если запрошен конкретный бар
    if bar_id and bar_id in bars_data:
        bars_data = {bar_id: bars_data[bar_id]}

    result_parts = []

    for b_id, bar_data in bars_data.items():
        bar_name = bar_data['name']
        taps = sorted(bar_data['taps'], key=lambda x: x.get('tap_number', 0))

        lines = [f"🍺 <b>{bar_name}</b>", ""]

        for tap in taps:
            tap_num = tap.get('tap_number', '?')

            if tap.get('mapped'):
                brewery = tap.get('brewery', '')
                name = tap.get('beer_name', tap.get('iiko_name', ''))
                style = tap.get('style', '')
                abv = tap.get('abv', '')
                ibu = tap.get('ibu', '')
                untappd = tap.get('untappd_url', '')

                line = f"<b>{tap_num}.</b> {brewery} — {name}"

                details = []
                if style:
                    details.append(style)
                if abv:
                    details.append(f"ABV {abv}")
                if ibu:
                    details.append(f"IBU {ibu}")

                if details:
                    line += f"\n    <i>{' | '.join(details)}</i>"
                if untappd:
                    line += f"\n    <a href='{untappd}'>Untappd</a>"
            else:
                # Нет маппинга - показываем название из iiko
                iiko_name = tap.get('iiko_name', 'Неизвестно')
                line = f"<b>{tap_num}.</b> {iiko_name}"

            lines.append(line)

        result_parts.append("\n".join(lines))

    if not result_parts:
        return "Нет данных о кранах"

    separator = "\n\n" + "━" * 25 + "\n\n"
    return separator.join(result_parts)


def get_bars_keyboard() -> InlineKeyboardMarkup:
    """Создать клавиатуру выбора бара"""
    buttons = []
    for bar_id, bar_name in BARS_CONFIG.items():
        buttons.append([InlineKeyboardButton(text=f"🍺 {bar_name}", callback_data=f"taplist_{bar_id}")])
    buttons.append([InlineKeyboardButton(text="📋 Все бары", callback_data="taplist_all")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
        "<i>Информация включает: пивоварню, название, стиль, ABV, IBU и ссылку на Untappd</i>",
        parse_mode="HTML"
    )


@dp.message(Command("taplist"))
async def cmd_taplist(message: types.Message):
    """Команда /taplist — показать выбор бара"""
    await message.answer(
        "🍺 Выберите бар:",
        reply_markup=get_bars_keyboard()
    )


async def send_taplist(message: types.Message, bar_id: str = None):
    """Отправить таплист"""
    loading_msg = await message.answer("⏳ Загрузка таплиста...")

    data = await fetch_taplist(bar_id)
    text = format_taplist_message(data, bar_id)

    await loading_msg.delete()

    # Если сообщение слишком длинное - разбиваем
    if len(text) > 4000:
        # Отправляем по барам
        for b_id in BARS_CONFIG.keys():
            bar_data = await fetch_taplist(b_id)
            bar_text = format_taplist_message(bar_data, b_id)
            if bar_text and "Нет активных" not in bar_text:
                await message.answer(bar_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@dp.message(Command("taplist1"))
async def cmd_taplist1(message: types.Message):
    await send_taplist(message, 'bar1')


@dp.message(Command("taplist2"))
async def cmd_taplist2(message: types.Message):
    await send_taplist(message, 'bar2')


@dp.message(Command("taplist3"))
async def cmd_taplist3(message: types.Message):
    await send_taplist(message, 'bar3')


@dp.message(Command("taplist4"))
async def cmd_taplist4(message: types.Message):
    await send_taplist(message, 'bar4')


@dp.message(Command("taplistall"))
async def cmd_taplist_all(message: types.Message):
    await send_taplist(message, None)


@dp.callback_query(lambda c: c.data.startswith('taplist_'))
async def process_taplist_callback(callback: types.CallbackQuery):
    """Обработка выбора бара"""
    bar_id = callback.data.replace('taplist_', '')

    await callback.answer("Загрузка...")

    if bar_id == 'all':
        data = await fetch_taplist(None)
    else:
        data = await fetch_taplist(bar_id)

    text = format_taplist_message(data, bar_id if bar_id != 'all' else None)

    if len(text) > 4000:
        await callback.message.answer("Таплист большой, отправляю по барам:")
        for b_id in BARS_CONFIG.keys():
            bar_data = await fetch_taplist(b_id)
            bar_text = format_taplist_message(bar_data, b_id)
            if bar_text and "Нет активных" not in bar_text:
                await callback.message.answer(bar_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


async def main():
    """Запуск бота"""
    logger.info(f"Запуск бота... API: {API_BASE_URL}")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

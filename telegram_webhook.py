"""
Telegram бот для KULT Taplist - Webhook версия
Работает внутри Flask приложения без отдельного процесса
"""
import os
import json
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Update

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8261982160:AAFu1YfpSQBB1lRC_gDxobwBfSL5kI0UKK8')

# Конфигурация баров
BARS_CONFIG = {
    'bar1': 'Большой пр. В.О',
    'bar2': 'Лиговский',
    'bar3': 'Кременчугская',
    'bar4': 'Варшавская',
}

# Инициализация бота (без polling)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_taplist_data(bar_id=None, taps_manager=None, beer_mapping=None):
    """
    Получить данные таплиста напрямую из taps_manager
    Работает локально без HTTP запросов
    """
    if not taps_manager:
        return None

    result = {
        'success': True,
        'taplist': []
    }

    bars = taps_manager.get_bars()
    if isinstance(bars, dict) and 'error' in bars:
        return None

    # Если запрошен конкретный бар
    if bar_id:
        bars = [b for b in bars if b.get('bar_id') == bar_id]

    for bar in bars:
        b_id = bar['bar_id']
        bar_name = bar['name']

        bar_data = taps_manager.get_bar_taps(b_id)
        if 'error' in bar_data:
            continue

        for tap in bar_data.get('taps', []):
            if tap.get('status') != 'active':
                continue

            beer_name = tap.get('current_beer')
            if not beer_name:
                continue

            tap_info = {
                'bar_id': b_id,
                'bar': bar_name,
                'tap_number': tap['tap_number'],
                'iiko_name': beer_name,
                'mapped': False
            }

            # Ищем маппинг пива
            if beer_mapping:
                beer_info = find_beer_info_local(beer_name, beer_mapping)
                if beer_info:
                    tap_info.update({
                        'mapped': True,
                        'brewery': beer_info.get('brewery', ''),
                        'beer_name': beer_info.get('beer_name', ''),
                        'untappd_url': beer_info.get('untappd_url', ''),
                        'style': beer_info.get('style', ''),
                        'abv': beer_info.get('abv', ''),
                        'ibu': beer_info.get('ibu', ''),
                        'description': beer_info.get('description', '')
                    })

            result['taplist'].append(tap_info)

    return result


def find_beer_info_local(beer_name, mapping):
    """Ищет информацию о пиве в маппинге"""
    if not beer_name or not mapping:
        return None

    import re

    def clean_name(name):
        """Очищает название от типичных суффиксов"""
        # Убираем "КЕГ "
        name = name.replace('КЕГ ', '').strip()
        # Убираем ", светлое", ", темное", ", нефильтрованное" и т.д.
        name = re.sub(r',\s*(светлое|темное|тёмное|нефильтрованное|фильтрованное|пшеничное)$', '', name, flags=re.IGNORECASE).strip()
        # Убираем объем в конце (30 л, 20л, 50L)
        name = re.sub(r'\s*\d+\s*(л|l|кг|kg)\s*$', '', name, flags=re.IGNORECASE).strip()
        return name

    # Прямое совпадение
    if beer_name in mapping:
        return mapping[beer_name]

    # Очищенное название
    cleaned = clean_name(beer_name)
    if cleaned in mapping:
        return mapping[cleaned]

    # Без "КЕГ "
    name_without_keg = beer_name.replace('КЕГ ', '').strip()
    if name_without_keg in mapping:
        return mapping[name_without_keg]

    # С "КЕГ "
    name_with_keg = f"КЕГ {beer_name}"
    if name_with_keg in mapping:
        return mapping[name_with_keg]

    # Частичное совпадение без объема
    name_base = re.sub(r'\s*\d+\s*(л|l|кг|kg)\s*$', '', beer_name, flags=re.IGNORECASE).strip()
    name_base = name_base.replace('КЕГ ', '').strip()

    for key in mapping:
        key_base = re.sub(r'\s*\d+\s*(л|l|кг|kg)\s*$', '', key, flags=re.IGNORECASE).strip()
        key_base = key_base.replace('КЕГ ', '').strip()
        if name_base.lower() == key_base.lower():
            return mapping[key]

    return None


def format_taplist_message(data, bar_id=None):
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


# Глобальные переменные для доступа к данным (будут установлены из app.py)
_taps_manager = None
_beer_mapping = None


def set_data_sources(taps_manager, beer_mapping):
    """Установить источники данных из Flask приложения"""
    global _taps_manager, _beer_mapping
    _taps_manager = taps_manager
    _beer_mapping = beer_mapping
    logger.info("Data sources set for Telegram bot")


async def send_taplist_response(message: types.Message, bar_id=None):
    """Отправить таплист"""
    data = get_taplist_data(bar_id, _taps_manager, _beer_mapping)
    text = format_taplist_message(data, bar_id)

    # Если сообщение слишком длинное - разбиваем
    if len(text) > 4000:
        for b_id in BARS_CONFIG.keys():
            bar_data = get_taplist_data(b_id, _taps_manager, _beer_mapping)
            bar_text = format_taplist_message(bar_data, b_id)
            if bar_text and "Нет активных" not in bar_text:
                await message.answer(bar_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
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

    if bar_id == 'all':
        data = get_taplist_data(None, _taps_manager, _beer_mapping)
        bar_id_for_format = None
    else:
        data = get_taplist_data(bar_id, _taps_manager, _beer_mapping)
        bar_id_for_format = bar_id

    text = format_taplist_message(data, bar_id_for_format)

    if len(text) > 4000:
        await callback.message.answer("Таплист большой, отправляю по барам:")
        for b_id in BARS_CONFIG.keys():
            bar_data = get_taplist_data(b_id, _taps_manager, _beer_mapping)
            bar_text = format_taplist_message(bar_data, b_id)
            if bar_text and "Нет активных" not in bar_text:
                await callback.message.answer(bar_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
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

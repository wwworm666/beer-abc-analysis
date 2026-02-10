"""
Entry point для VPS — polling mode (без Flask/webhook).
Запуск: python3 -m torrent_bot.run
"""
import telebot
from torrent_bot.config import BOT_TOKEN
from torrent_bot.bot import register_handlers

bot = telebot.TeleBot(BOT_TOKEN)
register_handlers(bot)

if __name__ == '__main__':
    print(f"Torrent Bot запущен (polling mode)")
    bot.remove_webhook()
    bot.infinity_polling(timeout=30, long_polling_timeout=30)

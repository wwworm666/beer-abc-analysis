"""
Torrent Bot — отдельный Flask-сервис.
Принимает webhook от Telegram, ищет фильмы, отправляет на Transmission.
"""
from flask import Flask, request, jsonify
import telebot
from torrent_bot.config import BOT_TOKEN, RENDER_EXTERNAL_URL, WEBHOOK_PATH
from torrent_bot.bot import register_handlers

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
register_handlers(bot)


@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    """Telegram отправляет сюда каждое сообщение."""
    update = telebot.types.Update.de_json(request.get_json())
    bot.process_new_updates([update])
    return '', 200


@app.route('/torrent-bot/health')
def health():
    return jsonify({'status': 'ok', 'service': 'torrent-bot'})


@app.route('/torrent-bot/set-webhook')
def set_webhook():
    """Вызвать один раз после деплоя для регистрации webhook в Telegram."""
    url = RENDER_EXTERNAL_URL
    if not url:
        return 'RENDER_EXTERNAL_URL not set', 500
    webhook_url = f'{url}{WEBHOOK_PATH}'
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    return f'Webhook set: {webhook_url}', 200

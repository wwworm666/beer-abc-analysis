import os

# Telegram
BOT_TOKEN = os.environ.get('TORRENT_BOT_TOKEN', '')

# Claude API
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL = 'claude-haiku-4-5-20251001'

# Transmission RPC (на роутере)
TRANSMISSION_HOST = os.environ.get('TRANSMISSION_HOST', 'localhost')
TRANSMISSION_PORT = int(os.environ.get('TRANSMISSION_PORT', '9091'))
TRANSMISSION_USER = os.environ.get('TRANSMISSION_USER', '')
TRANSMISSION_PASS = os.environ.get('TRANSMISSION_PASS', '')

# Трекеры
RUTRACKER_USER = os.environ.get('RUTRACKER_USER', '')
RUTRACKER_PASS = os.environ.get('RUTRACKER_PASS', '')
KINOZAL_USER = os.environ.get('KINOZAL_USER', '')
KINOZAL_PASS = os.environ.get('KINOZAL_PASS', '')

# Render
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
WEBHOOK_PATH = '/torrent-bot/webhook'

# Ограничение доступа (опционально — Telegram user ID)
ALLOWED_USERS = [int(x) for x in os.environ.get('ALLOWED_USERS', '').split(',') if x.strip()]

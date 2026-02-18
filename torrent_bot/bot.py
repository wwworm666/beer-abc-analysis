"""
Telegram bot — обработка сообщений, фото и inline-кнопок.
"""
import hashlib
import traceback
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from torrent_bot.config import ALLOWED_USERS
from torrent_bot.llm import identify_content, identify_from_results, rank_releases
from torrent_bot.trackers.search import search_all_trackers
from torrent_bot.transmission import add_torrent, get_torrents, remove_torrent

# Кэш результатов поиска (ключ → список релизов)
_results_cache = {}


def _format_title(movie):
    """Форматирует название с учётом типа (фильм/сериал)."""
    title = f"{movie.get('title_ru', '?')} ({movie.get('title_en', '')}, {movie.get('year', '')})"
    if movie.get('type') == 'series':
        season = movie.get('season')
        episode = movie.get('episode')
        if season:
            title += f" S{season:02d}" if isinstance(season, int) else f" S{season}"
            if episode:
                title += f"E{episode:02d}" if isinstance(episode, int) else f"E{episode}"
    return title


def _setup_commands(bot):
    """Устанавливает меню команд бота."""
    commands = [
        BotCommand('search', 'Поиск на трекерах'),
        BotCommand('list', 'Мои загрузки'),
        BotCommand('status', 'Статус загрузок'),
        BotCommand('help', 'Помощь'),
    ]
    try:
        bot.set_my_commands(commands)
    except Exception:
        pass


def register_handlers(bot):

    _setup_commands(bot)

    def is_allowed(message):
        if not ALLOWED_USERS:
            return True
        return message.from_user.id in ALLOWED_USERS

    def is_allowed_call(call):
        if not ALLOWED_USERS:
            return True
        return call.from_user.id in ALLOWED_USERS

    # ── /start ──────────────────────────────────────────────

    @bot.message_handler(commands=['start', 'help'])
    def handle_start(message):
        if not is_allowed(message):
            return
        bot.reply_to(message, (
            "Привет! Я найду и скачаю фильм или сериал.\n\n"
            "Что умею:\n"
            "- Напиши название: Inception\n"
            "- Опиши: тот фильм где ди каприо во сне\n"
            "- Отправь скриншот из фильма\n"
            "- Скриншот + подпись\n\n"
            "Команды:\n"
            "/search запрос — прямой поиск на трекерах\n"
            "/list — мои загрузки (удалить)\n"
            "/status — прогресс загрузок"
        ))

    # ── /status ─────────────────────────────────────────────

    @bot.message_handler(commands=['status'])
    def handle_status(message):
        if not is_allowed(message):
            return
        try:
            torrents = get_torrents()
            if not torrents:
                bot.reply_to(message, "Нет загрузок.")
                return
            lines = []
            for t in torrents:
                pct = int(t['progress'])
                bar = '█' * (pct // 10) + '░' * (10 - pct // 10)
                status_icon = '✅' if pct == 100 else '⏬'
                name = t['name']
                if len(name) > 40:
                    name = name[:37] + '...'
                lines.append(f"{status_icon} {bar} {pct}%\n   {name}")
            bot.reply_to(message, "\n\n".join(lines))
        except Exception as e:
            bot.reply_to(message, f"Ошибка Transmission: {e}")

    # ── /list — список загрузок с кнопками удаления ─────────

    @bot.message_handler(commands=['list'])
    def handle_list(message):
        if not is_allowed(message):
            return
        try:
            torrents = get_torrents()
            if not torrents:
                bot.reply_to(message, "Список пуст. Напиши название фильма чтобы найти и скачать.")
                return

            text = "Загрузки:\n\n"
            keyboard = InlineKeyboardMarkup()

            for i, t in enumerate(torrents):
                pct = int(t['progress'])
                status_icon = '✅' if pct == 100 else f'⏬ {pct}%'
                size = t.get('size', '?')
                name = t['name']
                if len(name) > 50:
                    name = name[:47] + '...'
                text += f"{i+1}. {status_icon} {name}\n   {size}\n\n"

                # Кнопка удаления
                keyboard.add(InlineKeyboardButton(
                    f"🗑 Удалить {i+1}: {name[:30]}",
                    callback_data=f"rm:{t['id']}"
                ))

            keyboard.add(InlineKeyboardButton("🗑 Удалить ВСЁ", callback_data="rm:all"))

            bot.reply_to(message, text, reply_markup=keyboard)
        except Exception as e:
            bot.reply_to(message, f"Ошибка Transmission: {e}")

    # ── /search — прямой поиск на трекерах ──────────────────

    @bot.message_handler(commands=['search'])
    def handle_search(message):
        if not is_allowed(message):
            return

        query = message.text.replace('/search', '', 1).strip()
        if not query:
            bot.reply_to(message, "Использование: /search название фильма")
            return

        chat_id = message.chat.id
        try:
            bot.send_chat_action(chat_id, 'typing')
            fake_movie = {'search_queries': [query], 'title_ru': query, 'title_en': '', 'year': ''}
            releases = search_all_trackers(fake_movie)

            if not releases:
                bot.reply_to(message, f"По запросу «{query}» ничего не нашёл.")
                return

            top = releases[:8]
            key = hashlib.md5(f"{chat_id}:{message.message_id}:s".encode()).hexdigest()[:8]
            _results_cache[key] = top

            text = f"Результаты по «{query}»:\n\n"
            keyboard = InlineKeyboardMarkup()

            for i, r in enumerate(top):
                seeds = r.get('seeds', '?')
                size = r.get('size', '?')
                title = r.get('title', '?')
                if len(title) > 60:
                    title = title[:57] + '...'
                text += f"{i+1}. {title}\n   {size} | {seeds} сидов\n\n"
                keyboard.add(InlineKeyboardButton(
                    f"{i+1}: {size} | {seeds}s",
                    callback_data=f"dl:{key}:{i}"
                ))

            keyboard.add(InlineKeyboardButton("Отмена", callback_data="cancel"))
            bot.reply_to(message, text, reply_markup=keyboard)

        except Exception as e:
            traceback.print_exc()
            bot.reply_to(message, f"Ошибка поиска: {e}")

    # ── Фото = скриншот из фильма ──────────────────────────

    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        if not is_allowed(message):
            return

        chat_id = message.chat.id
        caption = message.caption or None

        try:
            bot.send_chat_action(chat_id, 'typing')

            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            image_data = bot.download_file(file_info.file_path)

            ext = file_info.file_path.rsplit('.', 1)[-1].lower() if '.' in file_info.file_path else 'jpg'
            media_types = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif'}
            media_type = media_types.get(ext, 'image/jpeg')

            status_msg = bot.reply_to(message, "Анализирую скриншот...")

            movie = identify_content(user_text=caption, image_data=image_data, media_type=media_type)

            if not movie or movie.get('confidence', 0) < 0.4:
                reason = movie.get('reasoning', '') if movie else ''
                bot.edit_message_text(
                    f"Не смог определить фильм по скриншоту.\n{reason}\n\nПопробуй добавить подпись к фото или написать название.",
                    chat_id, status_msg.message_id
                )
                return

            _process_identified(bot, chat_id, message, status_msg, movie)

        except Exception as e:
            traceback.print_exc()
            bot.reply_to(message, f"Ошибка: {e}")

    # ── Текстовое сообщение = запрос фильма ─────────────────

    @bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
    def handle_movie_request(message):
        if not is_allowed(message):
            return

        chat_id = message.chat.id

        try:
            bot.send_chat_action(chat_id, 'typing')
            movie = identify_content(user_text=message.text)

            if not movie or movie.get('confidence', 0) < 0.5:
                bot.send_chat_action(chat_id, 'typing')
                fake_movie = {'search_queries': [message.text], 'title_ru': message.text, 'title_en': '', 'year': ''}
                raw_results = search_all_trackers(fake_movie)

                if raw_results:
                    match = identify_from_results(message.text, raw_results)
                    if match and match.get('confidence', 0) >= 0.5:
                        indices = match.get('matched_indices', [])
                        matched_releases = [raw_results[i-1] for i in indices if 1 <= i <= len(raw_results)]
                        if matched_releases:
                            movie_info = {
                                'title_ru': match.get('title_ru', message.text),
                                'title_en': match.get('title_en', ''),
                                'year': match.get('year', ''),
                                'type': match.get('type', 'movie'),
                            }
                            status_msg = bot.reply_to(message, f"Нашёл: {_format_title(movie_info)}\nРанжирую раздачи...")
                            ranked = rank_releases(movie_info, matched_releases)
                            _show_results(bot, chat_id, message, status_msg, movie_info, ranked)
                            return

                bot.reply_to(message,
                    "Не могу понять, какой фильм/сериал. Попробуй:\n"
                    "- Уточни название, год или режиссёра\n"
                    "- Отправь скриншот\n"
                    "- /search название — прямой поиск"
                )
                return

            status_msg = bot.reply_to(message, f"Ищу: {_format_title(movie)}\nПоиск по трекерам...")
            _process_identified(bot, chat_id, message, status_msg, movie)

        except Exception as e:
            traceback.print_exc()
            bot.reply_to(message, f"Ошибка: {e}")

    # ── Общая логика после определения фильма ───────────────

    def _process_identified(bot, chat_id, message, status_msg, movie):
        bot.send_chat_action(chat_id, 'typing')
        releases = search_all_trackers(movie)

        if not releases:
            fallback_movie = {'search_queries': [movie.get('title_ru', '')], 'title_ru': movie.get('title_ru', ''), 'title_en': '', 'year': ''}
            releases = search_all_trackers(fallback_movie)

        if not releases:
            bot.edit_message_text(
                f"{_format_title(movie)} — ничего не нашёл на трекерах.\n"
                f"Попробуй /search с другим запросом.",
                chat_id, status_msg.message_id
            )
            return

        ranked = rank_releases(movie, releases)
        _show_results(bot, chat_id, message, status_msg, movie, ranked)

    def _show_results(bot, chat_id, message, status_msg, movie, ranked):
        top = ranked[:10]

        key = hashlib.md5(f"{chat_id}:{message.message_id}".encode()).hexdigest()[:8]
        _results_cache[key] = top

        title = _format_title(movie)
        reasoning = movie.get('reasoning', '')
        text = f"{title}\n"
        if reasoning:
            text += f"({reasoning})\n"
        text += "\n"

        keyboard = InlineKeyboardMarkup()

        for i, r in enumerate(top):
            seeds = r.get('seeds', '?')
            text += (
                f"{i+1}. {r.get('quality', '?')} | "
                f"{r.get('size', '?')} | "
                f"{seeds} сидов | "
                f"{r.get('tracker', '?')}\n"
            )
            keyboard.add(InlineKeyboardButton(
                f"Скачать {i+1}: {r.get('quality', '?')} ({r.get('size', '?')})",
                callback_data=f"dl:{key}:{i}"
            ))

        keyboard.add(InlineKeyboardButton("Отмена", callback_data="cancel"))

        bot.edit_message_text(
            text, chat_id, status_msg.message_id,
            reply_markup=keyboard
        )

    # ── Нажатие кнопки «Скачать» ───────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith('dl:'))
    def handle_download(call):
        if not is_allowed_call(call):
            return
        _, key, idx_str = call.data.split(':')
        idx = int(idx_str)

        results = _results_cache.get(key)
        if not results or idx >= len(results):
            bot.answer_callback_query(call.id, "Результаты устарели, поищи заново")
            return

        release = results[idx]

        try:
            add_torrent(release)
            bot.edit_message_text(
                f"⏬ Качаю: {release.get('title', 'фильм')}\n"
                f"{release.get('quality', '')} | {release.get('size', '')}\n\n"
                f"/list — посмотреть загрузки",
                call.message.chat.id, call.message.message_id
            )
        except Exception as e:
            bot.edit_message_text(
                f"Ошибка Transmission: {e}",
                call.message.chat.id, call.message.message_id
            )

    # ── Удаление торрента ──────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith('rm:'))
    def handle_remove(call):
        if not is_allowed_call(call):
            return

        target = call.data.split(':')[1]

        try:
            if target == 'all':
                # Подтверждение удаления всего
                keyboard = InlineKeyboardMarkup()
                keyboard.add(
                    InlineKeyboardButton("Да, удалить всё", callback_data="rmconfirm:all"),
                    InlineKeyboardButton("Отмена", callback_data="cancel")
                )
                bot.edit_message_text(
                    "Точно удалить ВСЕ загрузки и файлы?",
                    call.message.chat.id, call.message.message_id,
                    reply_markup=keyboard
                )
            else:
                torrent_id = int(target)
                # Подтверждение удаления одного
                keyboard = InlineKeyboardMarkup()
                keyboard.add(
                    InlineKeyboardButton("Удалить с файлами", callback_data=f"rmconfirm:{torrent_id}:data"),
                    InlineKeyboardButton("Только из списка", callback_data=f"rmconfirm:{torrent_id}:keep"),
                )
                keyboard.add(InlineKeyboardButton("Отмена", callback_data="cancel"))
                bot.edit_message_text(
                    "Как удалить?",
                    call.message.chat.id, call.message.message_id,
                    reply_markup=keyboard
                )
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('rmconfirm:'))
    def handle_remove_confirm(call):
        if not is_allowed_call(call):
            return

        parts = call.data.split(':')
        target = parts[1]

        try:
            if target == 'all':
                torrents = get_torrents()
                for t in torrents:
                    remove_torrent(t['id'], delete_data=True)
                bot.edit_message_text(
                    f"Удалено {len(torrents)} загрузок с файлами.",
                    call.message.chat.id, call.message.message_id
                )
            else:
                torrent_id = int(target)
                delete_data = len(parts) > 2 and parts[2] == 'data'
                remove_torrent(torrent_id, delete_data=delete_data)
                action = "с файлами" if delete_data else "из списка"
                bot.edit_message_text(
                    f"✅ Удалено {action}.\n/list — обновить список",
                    call.message.chat.id, call.message.message_id
                )
        except Exception as e:
            bot.edit_message_text(
                f"Ошибка удаления: {e}",
                call.message.chat.id, call.message.message_id
            )

    # ── Кнопка «Отмена» ────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel')
    def handle_cancel(call):
        bot.edit_message_text(
            "Отменено.",
            call.message.chat.id, call.message.message_id
        )

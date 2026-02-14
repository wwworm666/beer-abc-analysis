# Torrent Bot — Документация

## Что это

Telegram-бот, который принимает название фильма, описание или даже скриншот — и скачивает фильм на VPS. Под капотом Claude Sonnet 4.5 определяет фильм, ищет на Rutracker лучшую раздачу, отправляет в Transmission. Смотришь через Jellyfin на ТВ.

Одна фраза в Telegram — фильм на телевизоре.

---

## Архитектура

```
  Telegram (ты)
       │
       ▼
┌──────────────┐
│  Telegram    │  pyTelegramBotAPI (polling)
│  Bot         │  VPS: 103.85.115.227
└──────┬───────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
┌──────┐  ┌──────────┐
│Claude│  │ Rutracker│  BeautifulSoup парсинг
│Sonnet│  │ (Kinozal)│
│ 4.5  │  └────┬─────┘
└──────┘       │
               ▼
         ┌───────────┐
         │Transmission│  transmission-remote CLI
         │  daemon    │  Скачивает .torrent файлы
         └─────┬─────┘
               │
               ▼
         ┌───────────┐
         │ Jellyfin  │  Медиа-сервер → стрим на ТВ
         │  :8096    │
         └───────────┘
```

**Всё живёт на одном VPS** (1 CPU, 1 GB RAM, 100 GB SSD, Ubuntu 22.04). Docker не используем — памяти мало, systemd-сервис проще и легче.

---

## Файлы

```
torrent_bot/
├── run.py              ← Точка входа (polling mode)
├── app.py              ← Flask webhook mode (для Render, не используется)
├── config.py           ← Конфигурация из .env
├── bot.py              ← Telegram handlers: текст, фото, кнопки, удаление
├── llm.py              ← Claude API: Vision + identify + rank releases
├── transmission.py     ← Управление Transmission через CLI
├── trackers/
│   ├── search.py       ← Параллельный поиск по трекерам
│   ├── rutracker.py    ← Парсер Rutracker
│   └── kinozal.py      ← Парсер Kinozal (не активен)
├── requirements.txt    ← Зависимости Python
├── .env.example        ← Шаблон переменных окружения
└── DOCS.md             ← Этот файл
```

**На VPS** код лежит в `/opt/torrent-bot/`, Python venv в `/opt/torrent-bot/venv/`.

---

## Как работает

### Сценарий 1: Пишешь название

```
Ты: "Inception"
 └→ Claude: {title_ru: "Начало", year: 2010, confidence: 0.99}
     └→ Rutracker: поиск "Начало 2010", "Inception 2010"
         └→ Claude ранжирует: 1080p BDRip 8GB 45 сидов — лучший
             └→ Кнопки: [Скачать 1] [Скачать 2] [Отмена]
                 └→ Нажал → Transmission качает → Jellyfin показывает на ТВ
```

### Сценарий 2: Описываешь фильм

```
Ты: "тот фильм где ди каприо во сне"
 └→ Claude: "Inception" (confidence: 0.95)
     └→ далее как в сценарии 1
```

### Сценарий 3: Отправляешь скриншот

```
Ты: [фото из фильма]
 └→ Bot скачивает фото → base64
     └→ Claude Vision API анализирует кадр
         └→ Определяет фильм по актёрам/стилю/обстановке
             └→ далее как в сценарии 1
```

### Сценарий 4: Claude не уверен (fallback)

```
Ты: "новый сериал 2025 года про женщину"
 └→ Claude: confidence < 0.5 — не уверен
     └→ Ищем на трекере напрямую по тексту
         └→ Claude смотрит результаты и выбирает подходящие
             └→ Показывает кнопки
```

---

## Команды бота

| Команда | Что делает |
|---------|-----------|
| Текст | Определяет фильм/сериал через Claude, ищет, предлагает скачать |
| Фото | Анализирует скриншот через Claude Vision |
| Фото + подпись | Использует и картинку, и текст |
| `/search запрос` | Прямой поиск на трекерах (без Claude) |
| `/list` | Список загрузок с кнопками удаления |
| `/status` | Прогресс загрузок (полоски) |
| `/help` | Справка |

Меню команд автоматически устанавливается через BotFather API при старте бота.

---

## Удаление фильмов

`/list` показывает все загрузки с кнопками:
- **Удалить [название]** — для каждого торрента отдельно
- **Удалить ВСЁ** — с подтверждением

При удалении спрашивает:
- "Удалить с файлами" — удаляет торрент + скачанные файлы
- "Только из списка" — убирает из Transmission, файлы остаются

---

## Инфраструктура VPS

### Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| Torrent Bot | — | systemd, polling mode |
| Transmission | 9091 | Web UI + RPC |
| Jellyfin | 8096 | Медиа-стриминг на ТВ |
| Xray (VLESS) | 443 | VPN через Reality |
| WireGuard | 51820 | VPN (резервный) |
| SSH | 22 | Управление |

### Systemd-сервис бота

```ini
# /etc/systemd/system/torrent-bot.service
[Service]
WorkingDirectory=/opt/torrent-bot
ExecStart=/opt/torrent-bot/venv/bin/python -m torrent_bot.run
EnvironmentFile=/opt/torrent-bot/.env
Restart=always
RestartSec=10
```

Управление:
```bash
systemctl restart torrent-bot   # перезапуск
systemctl status torrent-bot    # статус
journalctl -u torrent-bot -f    # логи в реальном времени
```

### Transmission

Раздача отключена (upload limit: 1 KB/s, ratio limit: 0). Скорость скачивания ~20 МБ/с — лимит хостера, не Transmission.

---

## Технологии и почему именно они

| Что | Почему |
|-----|--------|
| **Claude Sonnet 4.5** | Мультимодальный (текст + картинки), отлично знает кино, русский язык |
| **pyTelegramBotAPI** | Простой, polling mode не требует домен/SSL |
| **BeautifulSoup** | Парсинг HTML трекеров, работает с кривой кодировкой |
| **transmission-remote CLI** | Python-библиотека `transmission_rpc` глючила, CLI стабилен |
| **Jellyfin** | Бесплатный медиа-сервер, стримит на ТВ |
| **Xray + VLESS Reality** | VPN замаскирован под HTTPS, не блокируется DPI |
| **systemd** | Автозапуск, рестарт при падении, логи из коробки |
| **Python venv** | Изоляция зависимостей без Docker (RAM мало) |

---

## Баги и решения

### transmission_rpc "invalid or corrupt torrent file"

**Проблема**: Python-библиотека `transmission_rpc` (v7) не могла добавить торрент — ни через base64, ни через `file://` (поддержку убрали в v7).

**Решение**: Выкинули библиотеку, используем `transmission-remote` CLI через `subprocess`. Сохраняем `.torrent` во временный файл, передаём через `-a`:

```python
fd, path = tempfile.mkstemp(suffix='.torrent')
os.write(fd, torrent_bytes)
os.close(fd)
_remote('-a', path)  # transmission-remote -a /tmp/xxx.torrent
os.unlink(path)
```

**Урок**: Когда библиотека глючит — CLI-обёртка через subprocess часто проще и надёжнее.

---

### Кракозябры в поиске (кодировка Rutracker)

**Проблема**: Результаты поиска приходили в Telegram как `ÐÐ°ÑÐ°Ð»Ð¾` вместо кириллицы.

**Причина**: `resp.text` с ручной установкой `resp.encoding = 'utf-8'` не помогал — requests криво определял кодировку.

**Решение**: Передаём `resp.content` (сырые байты) в BeautifulSoup с явным `from_encoding`:

```python
# БЫЛО (кракозябры)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

# СТАЛО (работает)
soup = BeautifulSoup(resp.content, 'html.parser', from_encoding='utf-8')
```

**Урок**: `resp.text` — это `resp.content.decode(resp.apparent_encoding)`. Если `apparent_encoding` врёт — получишь мусор. Всегда передавай `content` + явную кодировку.

---

### WireGuard не работает / медленный

**Проблема**: WireGuard-протокол определяется и режется провайдерами (DPI).

**Решение**: Поставили Xray с VLESS + Reality. Трафик маскируется под обычный HTTPS к microsoft.com. NekoBox как клиент на ПК/телефоне.

---

### SSH зависает на длинных командах

**Проблема**: SSH-сессии к VPS периодически подвисают, особенно на длинном выводе.

**Решение**: Короткие команды вместо длинных скриптов. `scp` для файлов вместо `cat > file << EOF`. `ServerAliveInterval=10` в SSH.

---

### PowerShell обрезает длинные paste

**Проблема**: Вставка длинных скриптов в PowerShell SSH обрезается после ~2000 символов.

**Решение**: Разбивать на части или использовать `scp` для передачи файлов.

---

## Claude API — ключевые решения

### Vision API для скриншотов

Картинка отправляется как base64 в массиве `content`:

```python
content = [
    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
    {"type": "text", "text": "Определи фильм по скриншоту..."}
]
```

### Два уровня идентификации

1. **identify_content()** — Claude пытается определить фильм по тексту/картинке
2. **identify_from_results()** — fallback: ищем на трекере, Claude выбирает из результатов

Это решает проблему, когда Claude не знает название (вышло после мая 2025), но может выбрать правильный результат из списка.

### Ранжирование раздач

Claude получает список раздач и сортирует по критериям:
1. Качество видео (2160p > 1080p > 720p)
2. Сиды >= 3
3. Русская дорожка
4. Разумный размер (не 50GB remux)
5. Для сериалов — нужный сезон

---

## Деплой

Обновление бота на VPS:

```bash
# С локальной машины
scp torrent_bot/bot.py root@103.85.115.227:/opt/torrent-bot/torrent_bot/bot.py
scp torrent_bot/llm.py root@103.85.115.227:/opt/torrent-bot/torrent_bot/llm.py

# На VPS
ssh root@103.85.115.227 "systemctl restart torrent-bot"
```

Проверка:
```bash
ssh root@103.85.115.227 "systemctl status torrent-bot"
ssh root@103.85.115.227 "journalctl -u torrent-bot --since '5 min ago'"
```

---

## Changelog

- 2026-02-11: Удаление фильмов из бота, меню команд, VLESS Reality VPN
- 2026-02-10: Claude Vision — скриншоты, улучшенные промпты, серии, fallback
- 2026-02-09: Jellyfin на VPS + ADB установка на Xiaomi TV
- 2026-02-08: Первый рабочий бот: текст → Claude → Rutracker → Transmission

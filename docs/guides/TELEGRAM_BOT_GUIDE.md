# Telegram Бот KULT Taplist - Руководство

## Бот: @kult_taplist_bot

---

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и список команд |
| `/taplist` | Меню выбора бара (кнопки) |
| `/taplist1` | Большой пр. В.О |
| `/taplist2` | Лиговский |
| `/taplist3` | Кременчугская |
| `/taplist4` | Варшавская |
| `/taplistall` | Все бары |

---

## Архитектура

```
┌─────────────────┐
│   Пользователь  │
│   Telegram      │
└────────┬────────┘
         │ /taplist
         ▼
┌─────────────────┐      POST /telegram/webhook
│  Telegram API   │ ──────────────────────────────┐
└─────────────────┘                               │
                                                  ▼
                              ┌───────────────────────────────┐
                              │     www.beerkultura.ru        │
                              │        (Flask app.py)         │
                              └───────────────┬───────────────┘
                                              │
                              ┌───────────────▼───────────────┐
                              │     telegram_webhook.py       │
                              │        (aiogram 3)            │
                              └───────────────┬───────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
         ┌──────────▼──────────┐   ┌──────────▼──────────┐   ┌──────────▼──────────┐
         │   taps_manager.py   │   │ beer_info_mapping   │   │   Fuzzy Matching    │
         │  /kultura/taps_data │   │       .json         │   │     (difflib)       │
         │      .json          │   │   (408 записей)     │   │                     │
         └─────────────────────┘   └──────────┬──────────┘   └─────────────────────┘
                                              │
                                   ┌──────────▼──────────┐
                                   │ kegs_full_list_     │
                                   │ updated.xlsx        │
                                   │ (исходная таблица)  │
                                   └─────────────────────┘
```

---

## Поток данных маппинга

### Этап 1: Источник данных (Excel)

**Файл:** `kegs_full_list_updated.xlsx`

Таблица содержит 408 записей с колонками:
- Название в iiko
- Пивоварня
- Название пива
- Untappd URL
- Стиль
- ABV
- IBU
- Описание

**Этот файл редактируется вручную** при добавлении нового пива.

---

### Этап 2: Конвертация в JSON (одноразово)

**Результат:** `data/beer_info_mapping.json`

Конвертация из Excel в JSON была выполнена один раз при создании системы.

**Формат JSON:**
```json
{
  "Название из iiko": {
    "brewery": "Пивоварня",
    "beer_name": "Название пива",
    "untappd_url": "https://untappd.com/b/...",
    "style": "IPA - New England",
    "abv": "6.5%",
    "ibu": "45",
    "description": "Описание пива"
  }
}
```

---

### Этап 3: Загрузка при старте приложения

**Файл:** `app.py` (строки 50-65)

```python
# Инициализируем Telegram бота (webhook режим)
import telegram_webhook

# Загружаем маппинг пива для бота
beer_mapping_file = 'data/beer_info_mapping.json'
with open(beer_mapping_file, 'r', encoding='utf-8') as f:
    beer_mapping_for_bot = json.load(f)

# Передаем источники данных в telegram модуль
telegram_webhook.set_data_sources(taps_manager, beer_mapping_for_bot)
```

**Маппинг загружается один раз** при старте Flask приложения.

---

### Этап 4: Fuzzy Matching при запросе

**Файл:** `telegram_webhook.py` → `find_beer_info_local()`

Когда пользователь запрашивает `/taplist`, происходит:

```
1. Получить краны из taps_manager
         │
         ▼
2. Для каждого крана с пивом:
   beer_name = "КЕГ Бланш де Намур, светлое"
         │
         ▼
3. Нормализация названия:
   - Убрать "КЕГ "
   - Убрать ", светлое"
   - Убрать объёмы (30 л)
   - Заменить тире на пробел
   Результат: "бланш де намур"
         │
         ▼
4. Поиск в mapping:
   a) Точное совпадение после нормализации
   b) Fuzzy match (difflib.SequenceMatcher)
   c) Порог ≥ 75% = совпадение
         │
         ▼
5. Найдено: "Бланш де Намур" → {brewery, style, abv, untappd_url}
         │
         ▼
6. Форматирование ответа для Telegram
```

---

## Три места использования маппинга

| # | Место | Файл | Функция |
|---|-------|------|---------|
| 1 | Telegram бот (webhook) | `telegram_webhook.py` | `find_beer_info_local()` |

**Осталось одно место.** Таплист V2 (`/api/taps/taplist-full` и CSV-экспорт) с
20.09.2026 работает не по названиям, а по явной связи GUID товара iiko → ID
Untappd из проверенного реестра. Fuzzy matching оттуда удалён вместе с функцией
`find_beer_info()`: подбор по похожему названию подставлял гостю чужой сорт.
Описанный ниже алгоритм относится только к `telegram_webhook.py`.

Бот `telegram_bot.py` запрашивает таплист с `prices=false` — цены он не выводит,
а живой прайс стоил бы шести обращений к iiko на каждый запрос.

---

## Алгоритм Fuzzy Matching

```python
def normalize(name):
    """Нормализует название для сравнения"""
    name = name.lower()
    name = name.replace('кег ', '')                    # КЕГ
    name = name.replace(' — ', ' ').replace('-', ' ')  # Тире
    name = name.replace(',', '').replace('.', '')      # Пунктуация
    name = re.sub(r'\d+\s*(л|l|кг|kg|ml|мл)', '', name) # Объёмы
    # Суффиксы
    for suffix in ['светлое', 'темное', 'нефильтрованное', ...]:
        name = name.replace(suffix, '')
    return ' '.join(name.split()).strip()

def similarity(a, b):
    """difflib.SequenceMatcher"""
    return SequenceMatcher(None, a, b).ratio()

# Поиск
threshold = 0.75  # 75%
for key in mapping:
    score = similarity(normalize(beer_name), normalize(key))
    if score >= threshold:
        return mapping[key]  # Найдено!
```

**Примеры:**
```
"КЕГ Бланш де Намур, светлое" → "бланш де намур" → "Бланш де Намур" ✓
"КЕГ Гулден Драк 708, 20 л"   → "гулден драк 708" → "Гулден Драк 708 20 л" ✓
"Бюльви — Рустик полусухой"   → "бюльви рустик"  → "Бюльви Рустик полусухой" ✓
```

---

## Добавление нового пива

### Вариант 1: Редактирование JSON напрямую

**Файл:** `data/beer_info_mapping.json`

```json
{
  "Новое пиво 30 л": {
    "brewery": "Пивоварня",
    "beer_name": "Новое пиво",
    "untappd_url": "https://untappd.com/b/...",
    "style": "IPA",
    "abv": "6%",
    "ibu": "50",
    "description": "Описание"
  }
}
```

**После редактирования:**
1. Commit & push в GitHub
2. Render автоматически задеплоит
3. Бот начнёт использовать новые данные

---

### Вариант 2: Обновление Excel и конвертация

1. Редактировать `kegs_full_list_updated.xlsx`
2. Конвертировать в JSON (скрипт или вручную)
3. Заменить `data/beer_info_mapping.json`
4. Commit & push

---

## Файлы системы

```
beer-abc-analysis/
├── telegram_webhook.py          # Обработчики команд бота
├── telegram_bot.py              # Polling версия (для локальной разработки)
├── app.py                       # Flask + webhook endpoints
│
├── data/
│   └── beer_info_mapping.json   # 408 записей маппинга ← ИСПОЛЬЗУЕТСЯ
│
├── kegs_full_list_updated.xlsx  # Исходная таблица ← РЕДАКТИРОВАТЬ ЗДЕСЬ
│
└── /kultura/                    # Render Disk
    └── taps_data.json           # Данные о кранах
```

---

## Webhook настройка

### Установка webhook (один раз)

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://www.beerkultura.ru/telegram/webhook"
```

### Проверка статуса

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

### Удаление webhook (для локальной разработки)

```bash
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"
```

После удаления можно запустить `telegram_bot.py` в polling режиме.

---

## Локальная разработка

Токен никогда не пишем в команду буквально: значение остаётся в истории shell,
в списке процессов и в любом тексте, который потом попадёт в репозиторий. Читаем
его из окружения.

```bash
# Ввести токен скрыто: символы не отображаются и не попадают в history.
read -rs TELEGRAM_BOT_TOKEN && export TELEGRAM_BOT_TOKEN

# 1. Удалить webhook
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"

# 2. Запустить polling режим
python telegram_bot.py

# 3. Тестировать бота

# 4. После тестирования - вернуть webhook
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=https://www.beerkultura.ru/telegram/webhook"

# 5. Убрать токен из окружения текущей сессии
unset TELEGRAM_BOT_TOKEN
```

Переставить вебхук можно и не держа токен у себя вовсе: Actions →
«Telegram webhook» → Run workflow, действие `setWebhook` или `deleteWebhook`.
Workflow берёт значение из секрета `TELEGRAM_BOT_TOKEN` репозитория.

---

## Переменные окружения

Значения токенов в документации не приводятся — только места хранения.

| Переменная | Где лежит значение |
|------------|--------------------|
| `TELEGRAM_BOT_TOKEN` | `.env` на сервере (подключается через `env_file` в `docker-compose.yml`); копия — в GitHub Secrets репозитория для workflow «Telegram webhook» |
| `TELEGRAM_GROUP_CHAT_ID` | там же, в `.env` сервера |

Ротация токена по шагам, с командами для Windows — в
[secrets-rotation.md](secrets-rotation.md). Коротко: `@BotFather` → `/revoke`,
новое значение в `/opt/beer/.env` на сервере, `docker compose up -d --no-build app`,
затем обновить секрет `TELEGRAM_BOT_TOKEN` в Settings → Secrets and variables →
Actions. Список переменных проекта — в [.env.example](../../.env.example).

---

## Логи и отладка

В Render Dashboard → Logs искать:

```
[TELEGRAM] Загружен маппинг пива: 408 записей
[TELEGRAM] Бот инициализирован (webhook режим)
```

При ошибках:
```
[TELEGRAM WEBHOOK ERROR] ...
ERROR:telegram_webhook:Error processing update: ...
```

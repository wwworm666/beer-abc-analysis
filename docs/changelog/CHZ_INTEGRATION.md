# Интеграция с Честный ЗНАК API — Получение сроков годности пива

**Дата:** 2026-03-27 — 2026-04-05
**Статус:** ✅ Аутентификация работает, получение данных работает
**Папка проекта:** `chz_test/`
**Входная точка:** `chz_test/chz.py`

---

## Что это

Клиент для Честного Знака (ЧЗ) API, который позволяет:
1. Аутентифицироваться через УКЭП (ЭЦП) на Рутокене через CryptoPro CSP
2. Получить JWT токен (действует 9 часов)
3. Запросить коды маркировки пива со сроками годности
4. Сгруппировать данные по товару (GTIN) для отчёта

Используется для автоматического получения данных о сроках годности пива ООО "ИНВЕСТАГРО" (ИНН 7801630649) для последующего мониторинга на дашборде.

---

## Файлы

```
chz_test/
├── chz.py           ← Единый скрипт: auth + запросы + отчёты
├── README.md        ← Краткая инструкция
├── requirements.txt ← Зависимости
├── debug/           ← Рабочая папка (токен, промежуточные данные)
└── чз/              ← Документация API ЧЗ (HTML, для справки)
```

---

## Как работает

### Аутентификация (самая важная часть)

ЧЗ использует двухэтапную аутентификацию через УКЭП:

1. `GET /api/v3/true-api/auth/key` → сервер возвращает `{"uuid": "...", "data": "случайная_строка_30_символов"}`
2. Подписываем `data` с помощью УКЭП на Рутокене
3. `POST /api/v3/true-api/auth/simpleSignIn` с `{"uuid": uuid, "data": подпись}` → получаем JWT токен

### Рабочая формула подписи (найдено экспериментально)

```
csptest.exe -sfsign -sign -detached \
  -my "2297e52c1066bcaab8a9708a66935e56d9761fc2" \
  -in data.txt -out sig.txt -base64 \
  -cades_strict -add
```

Критические флаги:
- `-detached` — отсоединённая подпись
- `-cades_strict` — генерирует signingCertificateV2 атрибут (обязателен для CAdES-BES)
- `-add` — добавляет сертификат в PKCS#7 (цепочка доверия)
- `-base64` — вывод в base64

Формат отправки: `{"uuid": "...", "data": "подпись_base64"}`
**Не v3 формат (unitedToken) — он НЕ работает.**

### Запрос данных

```
POST /api/v4/true-api/cises/search
{
  "page": 0,
  "limit": 100,
  "filter": {
    "productGroups": ["beer"],
    "ownerInn": "7801630649",
    "introducedDatePeriod": {
      "from": "2026-03-01T00:00:00.000Z",
      "to": "2026-04-05T23:59:59.999Z"
    }
  }
}
```

Ответ: `{"result": [...], "isLastPage": true/false}`

Каждый элемент `result` содержит:
- `cis` — код маркировки
- `gtin` — GTIN товара
- `expirationDate` — срок годности (формат: `YYYY-MM-DDTHH:MM:SSZ`)
- `productionDate` — дата производства
- `status` — статус (INTRODUCED / RETIRED)
- `producerInn` — ИНН производителя
- `modId` — идентификатор партии

### Формат ответа

АПИ v4 возвращает данные в ключе `"result"` (не `"products"` как у v3).

---

## Команды

```cmd
cd C:\chz_test

# Обновить токен
python chz.py token

# Проверить организацию
python chz.py participants

# Поиск кодов (последние 30 дней)
python chz.py search

# Поиск с даты
python chz.py search 2026-03-01

# Период
python chz.py search 2026-03-01 2026-04-05

# Полный отчёт (загружает все страницы)
python chz.py report 2026-03-01 2026-04-05
```

---

## Параметры интеграции

| Параметр | Значение |
|----------|----------|
| Организaция | ООО "ИНВЕСТАГРО" |
| ИНН организации | 7801630649 |
| Сертификат владельца | 2297e52c1066bcaab8a9708a66935e56d9761fc2 |
| Владелец сертификата | Верещагин Егор Вячеславович |
| Продуктовая группа | beer |
| Базовый URL | https://markirovka.crpt.ru/api/v3/true-api |
| URL поиска (v4) | https://markirovka.crpt.ru/api/v4/true-api |

---

## Известные ограничения и подводные камни

1. **Запуск от имени администратора обязателен** — CSP требует доступ к Рутокену
2. **Токен действует 9 часов** (с запасом от реальных 10 часов)
3. **Пагинация** — API отдаёт по 100 кодов за запрос, `delay=2с` между страницами
4. **`filter` обязателен** — без фильтра запрос возвращает 400
5. **`cises/search` возвращает в `"result"`** — не `"products"`, это частая ошибка
6. **DDoS риск** — без задержки API банит (150+ страниц без паузы = соединение сбрасывается)
7. **Без `introducedDatePeriod`** возвращает ВСЕ коды с самого начала (может быть 15000+ записей)

---

## Для интеграции в основной проект (app.py)

```python
import sys, os
sys.path.insert(0, os.path.join(BASE_DIR, 'chz_test'))

from chz import load_token, make_request, INN_ORG

def get_chz_expiration(product_group="beer", date_from=None, date_to=None):
    """Получить данные о сроках годности из ЧЗ."""
    token = load_token()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "page": 0,
        "limit": 100,
        "filter": {
            "productGroups": [product_group],
            "ownerInn": INN_ORG,
            "introducedDatePeriod": {
                "from": f"{date_from}T00:00:00.000Z",
                "to": f"{date_to}T23:59:59.999Z"
            }
        }
    }

    url = "https://markirovka.crpt.ru/api/v4/true-api/cises/search"
    # ... pagination loop ...
    return items
```

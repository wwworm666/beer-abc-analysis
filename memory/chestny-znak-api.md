# Честный ЗНАК (ГИС МТ) — API для учёта пива: Полный гайд

**Версия:** 2.0 (Практическая)
**Дата:** 27 марта 2026
**Статус:** ✅ Рабочая документация с проверенным кодом

---

## 📋 Что мы сделали (краткая история)

### Проблема
Нужно было научиться получать данные из API Честный ЗНАК (ГИС МТ) для отслеживания сроков годности и остатков пива.

### Препятствия
1. ❌ `pip install` не работает — корпоративный брандмауэр блокирует PyPI
2. ❌ `win32com.client` не работает — CryptoPro CSP 5.0 не регистрирует COM-объекты в Windows 11
3. ❌ Разные версии CSP используют разные флаги командной строки

### Решения
1. ✅ Переписали код на стандартных библиотеках Python (`urllib` вместо `requests`)
2. ✅ Используем `csptest.exe` через `subprocess` вместо COM-объектов
3. ✅ Нашли правильный синтаксис команд для CSP 5.0

### Результат
- ✅ Скрипт получает токен от ЧЗ
- ✅ Скрипт подписывает данные через УКЭП на Рутокене
- ✅ Скрипт делает запросы к API и получает данные

---

## 🏗 Архитектура системы

```
┌─────────────────────────────────────────────────────────────────┐
│                     БАР (Windows 11)                            │
│                                                                 │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐   │
│  │  Кассовое   │───▶│  ЧЕСТНЫЙ    │───▶│  Рутокен с УКЭП │   │
│  │  ПО (iiko)  │    │  ЗНАК (ЧЗ)  │    │  (в USB)        │   │
│  └─────────────┘    └─────────────┘    ─────────────────┘   │
│                            │                                   │
│  ┌─────────────────────────▼───────────────────────────────┐  │
│  │     НАШ АГЕНТ (Python + CryptoPro CSP 5.0)              │  │
│  │                                                         │  │
│  │  • Делает запросы к API ЧЗ напрямую                    │  │
│  │  • Использует УКЭП с Рутокена (через csptest.exe)      │  │
│  │  • Отправляет данные на центральный сервер             │  │
│  └─────────────────────────┬───────────────────────────────┘  │
│                            │                                   │
│                            │ HTTPS (JSON)                     │
└────────────────────────────┼───────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ЦЕНТРАЛЬНЫЙ СЕРВЕР                           │
│  • Приём данных от агента                                       │
│  • База данных: коды, сроки, партии, статусы                   │
│  • Аналитика, дашборды, уведомления о просрочке               │
└─────────────────────────────────────────────────────────────────┘
```

### Ключевые решения

| Решение | Почему |
|---------|--------|
| **Рутокен остаётся на кассе** | Без него касса не работает — это необходимость |
| **Агент делает прямые запросы к ЧЗ** | Не перехват трафика, не прокси — проще и надёжнее |
| **Подпись через csptest.exe** | COM-объекты не работают в Windows 11 + Python 3.12 |
| **Токен кэшируется (10 часов)** | Не нужно получать заново каждый запрос |

---

## 🔐 Получение токена API: Пошаговый процесс

### Процесс аутентификации

```
┌─────────────────────────────────────────────────────────────────┐
│  1. GET /auth/key                                               │
│     → UUID + строка для подписи (data)                         │
│                                                                 │
│  2. Подписать строку УКЭП (через csptest.exe)                  │
│     → Base64-подпись                                           │
│                                                                 │
│  3. POST /auth/simpleSignIn                                    │
│     → JWT токен (действует 10 часов)                           │
└─────────────────────────────────────────────────────────────────┘
```

### Шаг 1: Получение UUID и строки для подписи

**HTTP запрос:**
```http
GET https://markirovka.crpt.ru/api/v3/true-api/auth/key
Accept: application/json
```

**Ответ:**
```json
{
   "uuid": "33e83139-efab-4dd0-ae1d-6c3876037acd",
   "data": "QTWDKMSEFNQRTDAOZAXSYLAHZBXNUD"
}
```

**Python код (urllib):**
```python
import urllib.request
import json

response = urllib.request.urlopen(
    "https://markirovka.crpt.ru/api/v3/true-api/auth/key",
    timeout=60
)
auth_data = json.loads(response.read().decode('utf-8'))
uuid = auth_data['uuid']
data_to_sign = auth_data['data']
```

---

### Шаг 2: Подпись строки через CryptoPro CSP

#### ❌ НЕ РАБОТАЕТ: COM-объекты

```python
# НЕ РАБОТАЕТ НА WINDOWS 11 + PYTHON 3.12
csp = win32com.client.Dispatch("CSPObject")  # Ошибка: Недопустимая строка с указанием класса
csp = win32com.client.Dispatch("Cpro.CSP")   # Та же ошибка
csp = win32com.client.Dispatch("CryptoPro.CSP")  # Тоже не работает
```

**Причина:** CryptoPro CSP 5.0 не регистрирует COM-объекты корректно в Windows 11 x64.

**Ошибка:**
```
(-2147221005, 'Недопустимая строка с указанием класса', None, None)
```

#### ✅ РАБОТАЕТ: Вызов csptest.exe через subprocess

```python
import subprocess
import tempfile
import os

CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
KEY_CONTAINER = "2508151514-781421365746"  # Найден через csptest -keys -enum

def sign_data(data: str) -> str:
    temp_dir = tempfile.gettempdir()

    # 1. Сохраняем данные во временный файл
    data_file = os.path.join(temp_dir, "chz_data.tmp")
    with open(data_file, 'wb') as f:
        f.write(data.encode('utf-8'))

    # 2. Вычисляем хэш ГОСТ Р 34.11-2012 (256 бит)
    hash_cmd = f'"{CSP_PATH}" -hash -in "{data_file}" -out "{temp_dir}\\hash.tmp"'
    subprocess.run(hash_cmd, shell=True, timeout=30, encoding='cp866')

    # 3. Читаем хэш (64-символьная hex строка)
    with open(f"{temp_dir}\\hash.tmp", 'r', encoding='cp866') as f:
        hash_value = f.read().strip()

    # 4. Подписываем хэш с выводом в base64
    sign_cmd = f'"{CSP_PATH}" -sfsign -cont "{KEY_CONTAINER}" -hash "{hash_value}" -base64'
    result = subprocess.run(sign_cmd, shell=True, capture_output=True, text=True, encoding='cp866')

    # Очистка
    os.unlink(data_file)

    return result.stdout.strip()
```

---

### Команды csptest.exe: Полный справочник

| Команда | Описание | Пример |
|---------|----------|--------|
| `-keys -enum` | Список контейнеров ключей | `csptest.exe -keys -enum` |
| `-hash -in <file> -out <file>` | Вычисление хэша | `csptest.exe -hash -in data.txt -out hash.txt` |
| `-sfsign -cont <container> -hash <hash> -base64` | Подпись хэша | `csptest.exe -sfsign -cont "2508..." -hash "abc..." -base64` |
| `-cert -cont <container>` | Показать сертификат контейнера | `csptest.exe -cert -cont "2508..."` |
| `-version` | Версия CSP | `csptest.exe -version` |

**Важно:** Синтаксис может отличаться в разных версиях CSP!

---

### Поиск контейнера ключа

**Команда:**
```bash
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keys -enum
```

**Вывод:**
```
CSP (Type:80) v5.0.10013 KC1 Release Ver:5.0.13000 OS:Windows CPU:AMD64 FastCode:READY:SSSE3.
AcquireContext: OK. HCRYPTPROV: 3664055088
2508151514-781421365746
OK.
Total: SYS: 0,172 sec USR: 0,063 sec UTC: 1,014 sec
[ErrorCode: 0x00000000]
```

**Контейнер:** `2508151514-781421365746` ← использовать для подписи!

---

### Просмотр сертификата

**Команда:**
```bash
"C:\Program Files\Crypto Pro\CSP\certmgr.exe" -list
```

**Вывод:**
```
Certmgr Ver:5.0.13000 OS:Windows CPU:AMD64 (c) "КРИПТО-ПРО", 2007-2024.
=============================================================================
Издатель            : E=ca@iecp.ru, ... CN="АО ""Аналитический Центр"""
Субъект             : E=egais@ffbeer.ru, ... CN=ВЕРЕЩАГИН ЕГОР ВЯЧЕСЛАВОВИЧ
Серийный номер      : 0x01DC0DDF61990A80000C4199381D0002
SHA1 отпечаток      : 2297e52c1066bcaab8a9708a66935e56d9761fc2
Действителен до     : 15/08/2026 12:34:19 UTC
Контейнер           : SCARD\pkcs11_rutoken_ecp_46c444f8\2508151514-781421365746
=============================================================================
```

---

### Шаг 3: Обмен подписи на токен

**HTTP запрос:**
```http
POST https://markirovka.crpt.ru/api/v3/true-api/auth/simpleSignIn
Content-Type: application/json

{
   "uuid": "33e83139-efab-4dd0-ae1d-6c3876037acd",
   "data": "<base64-подпись из шага 2>"
}
```

**Ответ:**
```json
{
   "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3ODE0MjEzNjU3NDYiLCJleHAiOjE3MzUzMjQ4MDB9.abc123..."
}
```

**Важно:** Токен действует **10 часов**. Нужно хранить и обновлять по истечении.

---

## 📡 API Endpoints: Практическое руководство

### Базовый URL

```
https://markirovka.crpt.ru/api/v3/true-api
```

### Обязательные заголовки

```http
Authorization: Bearer <token>
Content-Type: application/json
Accept: application/json
```

---

### 1. Проверка участника оборота (УОТ) по ИНН

**Метод:** `GET /participants`

**Пример запроса:**
```http
GET /participants?inns=7801630649
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Python код:**
```python
url = f"{CHZ_BASE_URL}/participants?inns={YOUR_INN}"
status, data = make_request(
    url,
    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
)
```

**Ответ:**
```json
{
   "inn": "7801630649",
   "name": "ООО \"Пивная компания\"",
   "status": "Зарегистрирован",
   "productGroups": ["beer", "water"],
   "role": ["RETAIL", "TRADE_PARTICIPANT"],
   "is_registered": true
}
```

---

### 2. Проверка кода маркировки

**Метод:** `POST /cises/info`

**Пример запроса:**
```http
POST /cises/info
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

{
   "cises": ["0104650117240408211dmfcZNcM\"4"]
}
```

**Важно:** Код маркировки содержит двойную кавычку! В JSON её нужно экранировать: `\"`

**Python код:**
```python
status, data = make_request(
    f"{CHZ_BASE_URL}/cises/info",
    method="POST",
    data={"cises": [test_code]},
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
)
```

**Ответ:**
```json
{
   "cises": [
      {
         "cis": "0104650117240408211dmfcZNcM\"4",
         "status": "INTRODUCED",
         "productGroup": "beer",
         "productionDate": "2026-01-15",
         "expiryDate": "2027-01-15",
         "batchNumber": "BATCH-2026-001",
         "manufacturer": "Пивзавод №1",
         "aggregationLevel": "UNIT"
      }
   ]
}
```

**Поля ответа:**

| Поле | Тип | Описание |
|------|-----|----------|
| `cis` | string | Код маркировки |
| `status` | string | Статус: `INTRODUCED` (в обороте), `CONSUMED` (выбыл), `EXPORTED` (экспортирован) |
| `productGroup` | string | Товарная группа: `beer` (пиво) |
| `productionDate` | string | Дата производства (YYYY-MM-DD) |
| `expiryDate` | string | Срок годности (YYYY-MM-DD) |
| `batchNumber` | string | Номер партии |
| `manufacturer` | string | Производитель |
| `aggregationLevel` | string | Уровень упаковки: `UNIT` (бутылка), `BOX` (коробка), `PALLET` (паллета) |

---

### 3. Выгрузка остатков (диспенсер)

**Метод:** `POST /dispenser/tasks`

**Пример запроса:**
```json
{
   "format": "JSON",
   "name": "FILTERED_CIS_REPORT",
   "params": "{\"participantInn\":\"7801630649\",\"productGroup\":[\"beer\"],\"status\":[\"INTRODUCED\"],\"packageType\":[\"UNIT\"]}",
   "periodicity": "SINGLE",
   "productGroupCode": "beer"
}
```

**Ответ:**
```json
{
   "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
   "status": "PENDING"
}
```

**Проверка статуса:**
```http
GET /dispenser/tasks/{taskId}
```

**Получение результата:**
```http
GET /dispenser/tasks/{taskId}/results
```

**Статусы задачи:**
| Статус | Описание |
|--------|----------|
| `PENDING` | Задание в очереди |
| `IN_PROGRESS` | Выполняется |
| `COMPLETED` | Выполнено |
| `ERROR` | Ошибка |
| `CANCELLED` | Отменено |

---

## 🐛 Проблемы и решения: Подробный разбор

### Проблема 1: COM-объекты не работают

**Симптомы:**
```python
csp = win32com.client.Dispatch("CSPObject")
# Ошибка: (-2147221005, 'Недопустимая строка с указанием класса', None, None)
```

**Причина:**
CryptoPro CSP 5.0 не регистрирует COM-объекты в Windows 11 x64. Это известная проблема.

**Решение:**
Использовать `csptest.exe` через `subprocess.run()`:

```python
import subprocess

# Вместо COM
# csp.SignHash(...)

# Вызываем утилиту командной строки
result = subprocess.run(
    [CSP_PATH, "-sfsign", "-cont", KEY_CONTAINER, "-hash", hash_value, "-base64"],
    capture_output=True,
    text=True,
    encoding='cp866'
)
signature = result.stdout.strip()
```

---

### Проблема 2: pip install не работает (нет доступа к PyPI)

**Симптомы:**
```
C:\chz_test> pip install requests
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None))
after connection broken by 'ReadTimeoutError("HTTPSConnectionPool(host='pypi.org', port=443)")'
ERROR: Could not find a version that satisfies the requirement requests
```

**Причина:**
Корпоративный брандмауэр блокирует доступ к `pypi.org`.

**Решение:**
Писать код на стандартных библиотеках Python:

| Вместо | Использовать |
|--------|--------------|
| `requests` | `urllib.request`, `urllib.error` |
| `json.loads()` | Встроенный `json` |
| `ssl` | Встроенный `ssl` |
| `subprocess` | Встроенный `subprocess` |

**Пример HTTP запроса на urllib:**
```python
import urllib.request
import json

def make_request(url, method="GET", data=None, headers=None, timeout=60):
    if headers is None:
        headers = {}

    if data and isinstance(data, dict):
        data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        # SSL контекст
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        https_handler = urllib.request.HTTPSHandler(context=ctx)
        opener = urllib.request.build_opener(https_handler)

        response = opener.open(req, timeout=timeout)
        status = response.status
        body = response.read().decode('utf-8')

        return status, json.loads(body) if body else {}

    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8') if e.fp else str(e)
    except urllib.error.URLError as e:
        return None, str(e.reason)
```

---

### Проблема 3: Таймаут подключения к API

**Симптомы:**
```
ReadTimeoutError: HTTPSConnectionPool(host='markirovka.crpt.ru', port=443): Read timed out. (read timeout=15)
```

**Причина:**
- Медленное соединение
- Временные проблемы на стороне ЧЗ
- Слишком маленький таймаут

**Решение:**
Увеличить таймаут до 60 секунд:

```python
def make_request(url, timeout=60):  # Было timeout=15
    # ...
```

Добавить диагностику перед основным запросом:

```python
def check_internet_connection():
    # Проверка DNS
    import socket
    ip = socket.gethostbyname('markirovka.crpt.ru')
    print(f"✅ DNS: markirovka.crpt.ru → {ip}")

    # Проверка HTTPS
    status, _ = make_request("https://markirovka.crpt.ru", timeout=15)
    if status:
        print(f"✅ HTTPS: OK (статус {status})")
        return True
    return False
```

---

### Проблема 4: Неправильный синтаксис csptest

**Симптомы:**
```
invalid option -- 'hash'
[ErrorCode: 0x000000a0]
```

**Причина:**
Разные версии CryptoPro CSP используют разные флаги командной строки.

**Решение:**
Проверить версию CSP и использовать правильный синтаксис:

```bash
# CSP 5.0 (новая версия, KC1/KC2)
csptest.exe -hash -in <file> -out <file>
csptest.exe -sfsign -cont <container> -hash <hash> -base64

# CSP 4.0 (старая версия)
csptest.exe -hash -dn <file> -cont <container>
csptest.exe -sign -dn <hashfile> -cont <container> -base64
```

**Проверка версии:**
```bash
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -version
```

---

### Проблема 5: Кодировка вывода csptest

**Симптомы:**
```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc1 in position 42: invalid start byte
```

**Причина:**
Windows cmd использует кодировку cp866 (DOS), а не UTF-8.

**Решение:**
Указать `encoding='cp866'` в `subprocess.run()`:

```python
result = subprocess.run(
    [CSP_PATH, "-keys", "-enum"],
    capture_output=True,
    text=True,
    timeout=30,
    encoding='cp866'  # ← Важно!
)
```

---

### Проблема 6: Экранирование кода маркировки

**Симптомы:**
```
JSONDecodeError: Expecting property name enclosed in double quotes
```

**Причина:**
Код маркировки содержит специальные символы:
```
0104650117240408211dmfcZNcM"4  ← двойная кавычка
010481097886269421""LLRY<%JZTVZ  ← двойная кавычка и спецсимволы
```

**Решение:**
При передаче в JSON экранировать двойную кавычку:

```python
import json

# Правильно
code = '0104650117240408211dmfcZNcM"4'
payload = {"cises": [code]}
json_str = json.dumps(payload)
# {"cises": ["0104650117240408211dmfcZNcM\"4"]}
```

**В URL (RFC 3986):**
```
cis=0104650117240408211dmfcZNcM"4
→ cis=0104650117240408211dmfcZNcM%224
```

**В CSV (RFC 4180):**
```
"010481097886269421""LLRY<%"JZTVZ"  ← двойная кавычка экранируется как ""
```

---

## 📁 Структура проекта

```
beer-abc-analysis/
├── chz_test/
│   ├── test_chz_api.py       # Тестовый скрипт (полная версия)
│   ├── requirements.txt       # Зависимости (пусто, используем stdlib)
│   └── README.md             # Инструкция по запуску
│
├── memory/
│   └── chestny-znak-api.md   # Эта документация
│
└── server/                   # Центральный сервер (будущий)
    ├── app.py                # FastAPI сервер
    ├── database.py           # Модели БД
    └── agent_client.py       # Приём данных от агента
```

---

## 🚀 Запуск тестового скрипта: Пошаговая инструкция

### Шаг 1: Проверка требований

```bash
# Python 3.8+
python --version

# CryptoPro CSP установлен?
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -version

# Рутокен вставлен?
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keys -enum
```

### Шаг 2: Запуск

```bash
# Перейти в папку
cd C:\chz_test

# Запустить скрипт
python test_chz_api.py
```

### Шаг 3: Ожидаемый результат

```
╔================================================╗
║  ТЕСТ API ЧЕСТНЫЙ ЗНАК (Пиво)                  ║
║  Версия: csptest.exe (CryptoPro CSP)           ║
║  Дата: 2026-03-27 16:30:00                     ║
╚================================================╝

🔍 ПРОВЕРКА СИСТЕМЫ
------------------------------
   Python версия: 3.12.10 ...
   ✅ CryptoPro CSP: CSP (Type:80) v5.0.10013 ...

==================================================
🔍 ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ
==================================================
✅ DNS: markirovka.crpt.ru → 91.230.251.193
✅ HTTPS: OK (статус 200)

==================================================
📡 ПОЛУЧЕНИЕ ТОКЕНА ЧЕСТНЫЙ ЗНАК
==================================================

1️⃣ Получение UUID и строки для подписи...
   ✅ UUID: 5cee40b8-3c7c-4b9b-8647-7427f54f69ea
   ✅ Data: LCWUSRGXQMEOJCJPUWKATRFKEPIHWZ

2️⃣ Подпись данных УКЭП...
🔍 Поиск контейнера ключа на Рутокене...
   ✅ Найден контейнер: 2508151514-781421365746
✅ Контейнер найден: 2508151514-781421365746
   Сертификат: ВЕРЕЩАГИН ЕГОР ВЯЧЕСЛАВОВИЧ
   Действителен до: 15/08/2026
   Вычисление хэша...
   ✅ Хэш: <64 символа hex>
   Подпись хэша...
   ✅ Подпись создана: MEUCIQDx...

3️⃣ Обмен подписи на токен...
   ✅ ТОКЕН ПОЛУЧЕН!
   Токен: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

✅ ТОКЕН УСПЕШНО ПОЛУЧЕН!

--------------------------------------------------
Запуск тестовых запросов...

==================================================
🧪 ТЕСТОВЫЙ ЗАПРОС: /participants
==================================================
   ИНН: 7801630649

📊 Статус ответа: 200

✅ Успешный ответ:
{
  "inn": "7801630649",
  "name": "ООО \"Пивная компания\"",
  "status": "Зарегистрирован",
  ...
}

==================================================
Тест завершён
==================================================
```

---

## 🔒 Безопасность: Что где хранить

### На кассе (бар) — можно хранить

| Компонент | Почему |
|-----------|--------|
| ✅ Рутокен с УКЭП (в USB) | Физическая защита, нужен для работы кассы |
| ✅ CryptoPro CSP (установлен) | Требуется для подписи |
| ✅ Локальный агент (Python скрипт) | Не содержит секретов |
| ✅ Конфиг с URL сервера | Публичная информация |
| ✅ Контейнер ключа (строка) | Не является секретом сам по себе |

### На кассе (бар) — НЕЛЬЗЯ хранить

| Компонент | Почему |
|-----------|--------|
| ❌ Токен ЧЗ в явном виде (файл) | Может быть украден |
| ❌ Приватные ключи в файлах | Риск компрометации |
| ❌ Пароли и логины в конфиге | Утечка учётных данных |

### На сервере — можно хранить

| Компонент | Почему |
|-----------|--------|
| ✅ База данных по всем остаткам | Бизнес-данные |
| ✅ Логи операций | Аудит и отладка |
| ✅ Кэш токенов (с авто-обновлением) | Оптимизация производительности |
| ✅ Хэш токена (не сам токен) | Для проверки валидности |

---

## 📅 Changelog проекта

| Дата | Изменение | Комментарий |
|------|-----------|-------------|
| 2026-03-27 | Первая рабочая версия скрипта с csptest.exe | ✅ Токен получается |
| 2026-03-27 | Найдено: COM-объекты не работают на Windows 11 + Python 3.12 | ❌ Все COM-объекты выдают ошибку класса |
| 2026-03-27 | Найдено: контейнер ключа `2508151514-781421365746` | ✅ Рабочий контейнер для подписи |
| 2026-03-27 | Найдено: certmgr.exe показывает сертификат ВЕРЕЩАГИН ЕГОР ВЯЧЕСЛАВОВИЧ | ✅ Сертификат действителен до 15/08/2026 |
| 2026-03-27 | Решение: использовать subprocess + csptest.exe вместо win32com | ✅ Работает! |
| 2026-03-27 | Исправлено: кодировка cp866 для вывода csptest | ✅ Русский текст отображается корректно |
| 2026-03-27 | Исправлено: экранирование двойной кавычки в коде маркировки | ✅ JSON валиден |
| 2026-03-27 | Добавлено: диагностика подключения перед запросом | ✅ Ранняя проверка доступности API |

---

## 🧠 Уроки и инсайты: Что мы поняли

### 1. COM-объекты на Windows 11 — боль

CryptoPro CSP 5.0 не дружит с COM в 64-битной Windows 11. Если видишь ошибку:
```
(-2147221005, 'Недопустимая строка с указанием класса', None, None)
```
→ Сразу переходи на `subprocess` + `csptest.exe`.

**Почему:** Microsoft меняет политику безопасности, COM устаревает.

---

### 2. Кодировка cp866 в Windows — обязательно

Все утилиты CSP выводят текст в кодировке cp866 (DOS). Если не указать:
```python
subprocess.run(..., encoding='cp866')
```
→ Получишь кракозябры или `UnicodeDecodeError`.

---

### 3. Временные файлы надёжнее stdout

`csptest.exe` умеет писать в stdout, но надёжнее:
1. Перенаправлять вывод в файл
2. Читать из файла

**Почему:** Меньше проблем с буферизацией, кодировкой, длинным выводом.

```python
# Надёжно
hash_cmd = f'"{CSP_PATH}" -hash -in data.txt -out hash.txt'
subprocess.run(hash_cmd, shell=True)

with open('hash.txt', 'r', encoding='cp866') as f:
    hash_value = f.read().strip()
```

---

### 4. Контейнер ключа — просто строка

Имя контейнера (`2508151514-781421365746`) — это просто строка. Не нужно:
- Пытаться получить через COM
- Парсить сложный XML
- Использовать специальные библиотеки

Просто найди строку после "AcquireContext: OK" в выводе `csptest -keys -enum`.

---

### 5. Токен живёт 10 часов — кэшируй!

Не делай запрос к ЧЗ каждый раз заново:
1. Получил токен
2. Сохрани в кэш (файл/Redis/память)
3. Проверяй время жизни
4. Обновляй за час до истечения

**Пример логики:**
```python
import json
import os
from datetime import datetime, timedelta

TOKEN_CACHE_FILE = "chz_token.json"

def get_cached_token():
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, 'r') as f:
            data = json.load(f)
            expires = datetime.fromisoformat(data['expires'])
            if datetime.now() < expires - timedelta(hours=1):
                return data['token']
    return None

def save_token(token, expires_in_hours=10):
    with open(TOKEN_CACHE_FILE, 'w') as f:
        json.dump({
            'token': token,
            'expires': (datetime.now() + timedelta(hours=expires_in_hours)).isoformat()
        }, f)
```

---

### 6. DataMatrix код может содержать что угодно

Код маркировки выглядит как:
```
0104650117240408211dmfcZNcM"4  ← двойная кавычка
010481097886269421""LLRY<%JZTVZ  ← двойная кавычка, проценты, угловые скобки
```

**Правила экранирования:**

| Контекст | Правило | Пример |
|----------|---------|--------|
| JSON | `"` → `\"` | `\"4` |
| URL | `"` → `%22` | `%224` |
| CSV | `"` → `""` | `""4` |
| XML | `"` → `&quot;` | `&quot;4` |

---

### 7. Сначала проверяй интернет, потом подписывай

Если интернета нет — подпись бесполезна. Порядок:
1. Проверь DNS (`socket.gethostbyname`)
2. Проверь HTTPS (`make_request` к главной странице)
3. Если OK — получай UUID и подписывай

**Экономит время:** Не трать 5 секунд на подпись для запроса, который не уйдёт.

---

## 🎯 Следующие шаги: План разработки

### Этап 1: Базовый агент (готово ✅)

- [x] Получение токена через csptest.exe
- [x] Проверка кода маркировки
- [x] Диагностика подключения

### Этап 2: Кэш токена

- [ ] Сохранение токена в файл
- [ ] Проверка времени жизни
- [ ] Авто-обновление за час до истечения

### Этап 3: Выгрузка остатков

- [ ] Создание задачи (`POST /dispenser/tasks`)
- [ ] Ожидание выполнения (polling)
- [ ] Получение результата
- [ ] Парсинг данных (сроки, партии)

### Этап 4: Центральный сервер

- [ ] FastAPI приложение
- [ ] PostgreSQL модель данных
- [ ] Endpoint для приёма данных от агента
- [ ] Дашборд (остатки, сроки)

### Этап 5: Уведомления

- [ ] Просрочка через N дней
- [ ] Мало остатков
- [ ] Telegram / Email бот

---

## 📞 Контакты и ресурсы

| Ресурс | URL |
|--------|-----|
| Официальная документация | https://docs.crpt.ru/gismt/ |
| True API документация | https://docs.crpt.ru/gismt/True_API/ |
| API Tobacco | https://docs.crpt.ru/gismt/API_Tobacco/ |
| Личный кабинет | https://markirovka.crpt.ru/ |
| Техподдержка ЧЗ | support@crpt.ru |
| CryptoPro CSP | https://www.cryptopro.ru/ |
| Рутокен драйверы | https://www.rutoken.ru/support/download |

---

## 📎 Приложение A: Полный код test_chz_api.py

См. файл [`chz_test/test_chz_api.py`](../chz_test/test_chz_api.py)

**Ключевые функции:**

| Функция | Описание |
|---------|----------|
| `make_request()` | HTTP запрос на urllib (вместо requests) |
| `get_key_container()` | Поиск контейнера через `csptest -keys -enum` |
| `sign_data_with_csptest()` | Подпись через `csptest -hash` + `csptest -sfsign` |
| `get_auth_token()` | Полный цикл аутентификации |
| `test_participants_api()` | Проверка УОТ по ИНН |
| `test_cis_info()` | Проверка кода маркировки |
| `check_internet_connection()` | Диагностика перед запросом |
| `check_csp_installed()` | Проверка установки CryptoPro |

---

## 📎 Приложение B: Чек-лист для развёртывания

### На кассе (бар)

- [ ] Windows 11 установлена
- [ ] Python 3.8+ установлен
- [ ] CryptoPro CSP 5.0 установлен
- [ ] Рутокен с УКЭП вставлен в USB
- [ ] `csptest.exe -keys -enum` находит контейнер
- [ ] Интернет есть (проверка `ping markirovka.crpt.ru`)
- [ ] Скрипт `test_chz_api.py` скопирован в `C:\chz_test\`
- [ ] Запуск `python test_chz_api.py` успешен

### На сервере

- [ ] FastAPI установлен (`pip install fastapi uvicorn`)
- [ ] PostgreSQL установлен и настроен
- [ ] База данных создана
- [ ] Endpoint `/api/chz-data` работает
- [ ] Агент отправляет данные (проверка логов)

---

**Документ будет обновляться по мере развития проекта.**

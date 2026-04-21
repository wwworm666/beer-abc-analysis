# Plan: CHZ Stock — получение сроков годности пива

## Цель
Получить данные о сроках годности пива из Честного Знака и сделать их доступными
через Flask API `/api/chz/stock`. Все данные берутся с бар-ПК через SSH.

## Контекст
- `chz_test/chz.py` — рабочий клиент ЧЗ (аутентификация через CryptoPro csptest.exe)
- `remote_exec.py` — SSH-клиент к бар-ПК (100.98.149.108, пользователь Администратор / Krem2026)
- Подпись (csptest.exe) работает ТОЛЬКО под учётной записью Администратор
- `chz_test/debug/chz_stock.json` — кеш данных (предыдущий успешный запуск: 38 GTIN)
- Python на бар-ПК: `C:\Users\1\AppData\Local\Python\bin\python.exe`
- Репозиторий на бар-ПК: `C:\Users\1\Documents\GitHub\beer-abc-analysis`
- Токен ЧЗ действует ~10 часов, обновляется автоматически при запуске chz.py

## Validation Commands
```
python remote_exec.py status
python -m py_compile chz_test/chz.py
python -m py_compile remote_exec.py
python -c "import json,os; d=json.load(open('chz_test/debug/chz_stock.json')); print('OK:', len(d), 'items,', sum(1 for x in d if x.get('expiration_dates')), 'with expiration dates')"
```

---

### Task 1: Проверить и восстановить SSH-подключение к бар-ПК

Запусти `python remote_exec.py status` и проверь вывод.
Если возвращает `STATUS: OFFLINE`:
- Проверь в remote_exec.py строки REMOTE_HOST, REMOTE_USER, REMOTE_PASS
- REMOTE_USER должен быть `Администратор`, REMOTE_PASS = `Krem2026`
- Попробуй альтернативные имена: `1` с паролем `qwe123` (бар-10 из CONNECTIVITY.md)
- Используй `paramiko.SSHClient` с `look_for_keys=False` и `allow_agent=False`
  чтобы исключить конфликты с ключами

Если `STATUS: ONLINE` — задача завершена.

- [x] Запустить `python remote_exec.py status`, убедиться что выводит `STATUS: ONLINE`
- [x] Если OFFLINE: исправить параметры подключения в remote_exec.py и повторить

---

### Task 2: Убедиться что chz.py и Python доступны на бар-ПК

Выполни через remote_exec:
```python
# В remote_exec.py, через run_cmd:
"C:\Users\1\AppData\Local\Python\bin\python.exe" --version
```

Если Python не найден по этому пути — найди его:
```
where python
dir C:\Users\1\AppData\Local\ /b
dir C:\Program Files\Python* /b
```

Обнови `REMOTE_PYTHON` в remote_exec.py на правильный путь.

Проверь что репозиторий есть:
```
dir C:\Users\1\Documents\GitHub\beer-abc-analysis\chz_test\chz.py
```

Если файл устарел — загрузи актуальный:
```python
push("chz_test/chz.py", "C:\\Users\\1\\Documents\\GitHub\\beer-abc-analysis\\chz_test")
```

- [x] Найти рабочий путь к Python на бар-ПК, обновить REMOTE_PYTHON в remote_exec.py
- [x] Убедиться что chz.py есть на бар-ПК (или загрузить)

---

### Task 3: Исправить get_all_cises — добавить дефолтный лимит по дате

**Файл:** `chz_test/chz.py`, функция `get_chz_stock`

Проблема: при вызове без `date_from` скачивает ВСЕ коды за всё время (90k+, не завершается).
Решение: добавить дефолтную дату 6 месяцев назад чтобы ограничить выборку.

В функции `get_chz_stock` (строка ~470):
```python
# Было:
if product_groups is None:
    groups = PRODUCT_GROUPS

# Стало (добавить ПОСЛЕ нормализации groups):
if date_from is None:
    date_from = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
```

Также убедиться что в `get_all_cises` переменная `limit = 1000` (не 100).
При limit=1000 и ~5000 активных кодов — это ~5 страниц, ~30 секунд.

- [x] В `get_chz_stock`: добавить `if date_from is None: date_from = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")`
- [x] Убедиться что `limit = 1000` в `get_all_cises` (проверить строку ~298)

---

### Task 4: Обновить токен и получить данные с бар-ПК

Используй `remote_exec.py` для выполнения на бар-ПК:

**Шаг 1 — обновить токен:**
```python
run_cmd(
    'cd C:\\Users\\1\\Documents\\GitHub\\beer-abc-analysis && '
    '"C:\\Users\\1\\AppData\\Local\\Python\\bin\\python.exe" chz_test\\chz.py token'
)
```

**Шаг 2 — запустить stock (2 года, все группы):**
```python
run_cmd(
    'cd C:\\Users\\1\\Documents\\GitHub\\beer-abc-analysis && '
    '"C:\\Users\\1\\AppData\\Local\\Python\\bin\\python.exe" chz_test\\chz.py stock',
    timeout=600  # 10 минут максимум
)
```

**Шаг 3 — забрать результат:**
```python
pull(
    "C:\\Users\\1\\Documents\\GitHub\\beer-abc-analysis\\chz_test\\debug\\chz_stock.json",
    "chz_test/debug/"
)
```

Добавить команду `run_cmd` с параметром `timeout` в remote_exec.py
(сейчас `timeout` не передаётся в `exec_command`).

В функции `run_cmd` добавить параметр `timeout=None` и передать в `exec_command`:
```python
stdin, stdout, stderr = client.exec_command(rem_cmd, get_pty=False, timeout=timeout)
```

- [x] Добавить параметр `timeout` в `run_cmd` функцию remote_exec.py
- [x] Добавить в remote_exec.py команду `run stock` которая:
  1. Запускает `chz.py stock 2024-01-01` на бар-ПК (timeout=600)
  2. Скачивает `chz_stock.json` в локальный `chz_test/debug/`
- [x] Запустить `python remote_exec.py run stock` и убедиться что chz_stock.json обновился
      (по умолчанию берёт последние 6 месяцев)

---

### Task 5: Добавить Flask-маршрут `/api/chz/stock`

**Файл:** `routes/stocks.py`

Добавить в конец файла новый endpoint:

```python
@stocks_bp.route('/api/chz/stock', methods=['GET'])
def get_chz_stock_api():
    """Остатки ЧЗ с датами годности. Читает из кеша chz_stock.json."""
    import os
    cache_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'chz_test', 'debug', 'chz_stock.json'
    )
    if not os.path.exists(cache_file):
        return jsonify({'items': [], 'updated_at': None, 'error': 'no data'})

    mtime = os.path.getmtime(cache_file)
    updated_at = datetime.fromtimestamp(mtime).isoformat()

    with open(cache_file, encoding='utf-8') as f:
        items = json.load(f)

    return jsonify({'items': items, 'updated_at': updated_at})
```

Метод `GET /api/chz/stock` возвращает:
```json
{
  "updated_at": "2026-04-21T12:00:00",
  "items": [
    {
      "gtin": "04660185917775",
      "name": "Пиво светлое...",
      "brand": "Polnochnyj Project",
      "count": 450,
      "expiration_dates": ["2027-03-10"],
      "production_dates": ["2026-03-10"],
      "product_group": "BEER"
    }
  ]
}
```

- [x] Добавить маршрут `GET /api/chz/stock` в `routes/stocks.py`
- [x] Endpoint читает `chz_test/debug/chz_stock.json` и возвращает JSON
- [x] Если файл не найден — возвращает `{"items": [], "updated_at": null, "error": "no data"}`
- [x] Добавить маршрут `POST /api/chz/refresh` который запускает `remote_exec.py run stock`
  в фоне (subprocess.Popen) и сразу возвращает `{"status": "started"}`

---

### Task 6: Проверить результат

Убедиться что данные доступны:

```bash
# Запустить Flask приложение (если есть app.py)
# python app.py &

# Проверить данные в JSON
python -c "
import json
d = json.load(open('chz_test/debug/chz_stock.json'))
beer = [x for x in d if 'BEER' in x.get('product_group','').upper() or 'beer' in x.get('product_group','').lower()]
print(f'Всего GTIN: {len(d)}')
print(f'Пиво: {len(beer)}')
for x in beer[:5]:
    print(f'  {x[\"gtin\"]} | {x.get(\"name\",\"\")[:50]} | срок: {x.get(\"expiration_dates\")}')
"
```

- [x] Запустить проверку Python: убедиться что в chz_stock.json есть пиво с датами годности
- [x] Убедиться что items содержат непустые `expiration_dates`
- [x] Убедиться что `python -m py_compile routes/stocks.py` проходит без ошибок

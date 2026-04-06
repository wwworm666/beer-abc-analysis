# Честный ЗНАК API — Сроки годности пива

Рабочий клиент ЧЗ API: аутентификация + получение сроков годности кодов маркировки пива.

## Что в папке

| Файл | Назначение |
|------|-----------|
| `chz.py` | **Единственный** скрипт: аутентификация + запрос данных |
| `debug/` | Рабочая папка (токен, промежуточные файлы) |
| `чз/` | Документация ЧЗ API (HTML, сохранена для справки) |
| `requirements.txt` | Зависимости: `requests`, `pycryptodome`, `pywin32` |

## Установка на бар-ПК

1. Скопируй папку в `C:\chz_test`
2. Открой cmd **ОТ ИМЕНИ АДМИНИСТРАТОРА**
3. `pip install -r C:\chz_test\requirements.txt`

## Требования

- **Рутокен с УКЭП** в USB
- **CryptoPro CSP 5.0+** (`csptest.exe`)
- **Python 3.10+**
- Интернет

## Команды

### Получить/обновить токен

```cmd
cd C:\chz_test
python chz.py token
```

Токен сохраняется в `debug\token.json`. Действует 9 часов.
`load_token()` автоматически обновит если истёк.

### Проверить организацию

```cmd
python chz.py participants
```

### Поиск кодов (50 штук, по умолчанию 30 дней назад)

```cmd
python chz.py search
```

С конкретной даты:

```cmd
python chz.py search 2026-03-01
```

Период:

```cmd
python chz.py search 2026-03-01 2026-04-05
```

### Полный отчёт с загрузкой всех страниц

```cmd
python chz.py report 2026-03-01 2026-04-05
```

Выводит по GTIN: количество кодов, срок годности, дата производства, MOD ID.
Сохраняет `debug\expiration_data.json` (сводка) и `debug\expiration_full.json` (все записи).

## Рабочая формула аутентификации

**Команда подписи:**

```
csptest.exe -sfsign -sign -detached -my "2297..." -in data.txt -out sig.txt -base64 -cades_strict -add
```

**Запрос в API:**

```
POST https://markirovka.crpt.ru/api/v3/true-api/auth/simpleSignIn
{"uuid": "uuid-из-key", "data": "подпись-base64"}
```

Критически важно:
- `-detached -cades_strict -add` (три флага обязательны)
- Формат **v2** (`{"uuid": ..., "data": ...}`), НЕ v3 (`unitedToken`)
- Запускать от имени администратора

## Программа для интеграции в основной проект

Импортируй `chz_auth_lib` (встроен в `chz.py` как модуль):

```python
from chz import load_token, make_request, CHZ_BASE_URL, INN_ORG

token = load_token()  # автоматически обновит если истёк

# Поиск кодов
headers = {"Authorization": f"Bearer {token}"}
payload = {
    "page": 0,
    "limit": 100,
    "filter": {
        "productGroups": ["beer"],
        "ownerInn": INN_ORG,
        "introducedDatePeriod": {
            "from": "2026-03-01T00:00:00.000Z",
            "to": "2026-04-05T23:59:59.999Z"
        }
    }
}
```

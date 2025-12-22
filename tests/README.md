# Tests

Тестовые скрипты и данные проекта.

## Структура

```
tests/
├── test_all_iiko_apis.py      # Тесты всех iiko API endpoints
├── test_weihenstephan_data.py # Тесты данных Weihenstephan
├── test_modules.html          # HTML страница тестирования модулей
└── exports/                   # Тестовые экспорты (игнорируется git)
```

## Запуск тестов

```bash
# Тест iiko API
python tests/test_all_iiko_apis.py

# Тест данных Weihenstephan
python tests/test_weihenstephan_data.py
```

## Тестовые экспорты

Папка `exports/` содержит тестовые экспорты данных и игнорируется git.

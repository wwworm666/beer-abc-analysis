# Структура проекта Beer ABC/XYZ Analysis

## Корневая директория

```
beer-abc-analysis/
├── app.py                  # Основное Flask приложение
├── config.py               # Конфигурация приложения
├── requirements.txt        # Python зависимости
├── render.yaml             # Конфигурация Render.com
├── telegram_bot.py         # Telegram бот (polling режим)
├── telegram_webhook.py     # Telegram бот (webhook режим)
├── README.md               # Главная документация
│
├── core/                   # Основные модули анализа
├── dashboardNovaev/        # Модули дашборда
├── mapping/                # Маппинг блюд на кеги
├── utils/                  # Утилиты маппинга
├── static/                 # Статические файлы (CSS, JS)
├── templates/              # HTML шаблоны
├── data/                   # Данные приложения
├── docs/                   # Документация
├── scripts/                # Вспомогательные скрипты
├── tests/                  # Тесты
└── archive/                # Архив старых скриптов
```

## Детальная структура

### `/core` - Основные модули
| Файл | Описание |
|------|----------|
| `abc_analysis.py` | ABC-анализ (выручка, наценка, маржа) |
| `xyz_analysis.py` | XYZ-анализ (стабильность спроса) |
| `olap_reports.py` | Работа с iiko OLAP API |
| `data_processor.py` | Обработка данных |
| `category_analysis.py` | Анализ по категориям |
| `draft_analysis.py` | Анализ разливного пива |
| `waiter_analysis.py` | Анализ по официантам |
| `taps_manager.py` | Управление кранами |
| `iiko_api.py` | Базовые вызовы iiko API |

### `/dashboardNovaev` - Дашборд
| Файл | Описание |
|------|----------|
| `dashboard_analysis.py` | Метрики дашборда |
| `plans_manager.py` | Управление планами |
| `weeks_generator.py` | Генератор недель |
| `backend/` | Вспомогательные модули бэкенда |

### `/data` - Данные
```
data/
├── plansdashboard.json     # Планы дашборда (основной файл)
├── taps_data.json          # Данные кранов (игнорируется git)
├── beer_info_mapping.json  # Маппинг информации о пиве
├── dish_to_keg_mapping.json # Маппинг блюд на кеги
├── cache/                  # Кэшированные данные
├── reports/                # Экспортированные отчеты
└── temp/                   # Временные файлы
```

### `/docs` - Документация
```
docs/
├── guides/                 # Руководства пользователя
│   ├── DEPLOYMENT_GUIDE.md
│   ├── BACKUP_SETUP.md
│   ├── TELEGRAM_BOT_GUIDE.md
│   ├── TAPS_*.md           # Документация по кранам
│   └── ИНСТРУКЦИЯ_*.md     # Инструкции на русском
│
├── technical/              # Техническая документация
│   ├── MAPPING_*.md        # Документация маппинга
│   ├── SYNC_FLOW_VISUAL.md
│   └── CODE_ANALYSIS_COMPLETE.md
│
├── changelog/              # История изменений
│   ├── CHANGELOG_*.md
│   ├── CRITICAL_FIXES_SUMMARY.md
│   └── *_BUG.md, *_FIX.md
│
├── iiko-api/               # Документация iiko API
│   ├── pdf/                # PDF версии
│   └── md/                 # Markdown версии
│
└── archive/                # Архивная документация
```

### `/scripts` - Вспомогательные скрипты
```
scripts/
├── debug/                  # Отладочные скрипты
│   └── debug_*.py          # Скрипты отладки конкретных баров/функций
│
├── check/                  # Скрипты проверки
│   └── check_*.py          # Проверка данных и функций
│
├── analysis/               # Скрипты анализа
│   ├── analyze_*.py
│   ├── calculate_*.py
│   └── search_*.py
│
├── import_export/          # Импорт/экспорт данных
│   ├── import_plans_*.py
│   └── export_*.py
│
└── maintenance/            # Обслуживание
    ├── backup.bat
    ├── daily_update_mapping.bat
    ├── convert_pdf_to_md.py
    └── create_*.py
```

### `/tests` - Тесты
```
tests/
├── test_all_iiko_apis.py   # Тесты iiko API
├── test_weihenstephan_data.py
├── test_modules.html       # HTML тест модулей
└── exports/                # Тестовые экспорты
```

### `/mapping` - Маппинг
| Файл | Описание |
|------|----------|
| `keg_mapping.py` | Логика маппинга кегов |
| `*.csv` | CSV файлы маппинга |

### `/utils` - Утилиты
| Файл | Описание |
|------|----------|
| `auto_add_new_dishes.py` | Автодобавление новых блюд |
| `check_unmapped_dishes.py` | Проверка немаппированных блюд |
| `import_final_mapping.py` | Импорт финального маппинга |

## Важные файлы конфигурации

| Файл | Описание |
|------|----------|
| `.env` | Переменные окружения (секреты, не в git) |
| `.env.example` | Пример .env файла |
| `.gitignore` | Игнорируемые файлы |
| `render.yaml` | Конфигурация деплоя на Render |
| `.python-version` | Версия Python для pyenv |

## Запуск проекта

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск приложения
python app.py

# Или через Flask
flask run
```

## Основные URL

- `/` - Главная страница
- `/dashboard` - Дашборд План vs Факт
- `/taps` - Управление кранами
- `/api/*` - API endpoints

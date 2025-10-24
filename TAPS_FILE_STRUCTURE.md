# Структура файлов системы управления пивными кранами

## 📂 Иерархия проекта

```
beer-abc-analysis/
│
├── 📄 app.py                                    ← Главное приложение Flask (ОБНОВЛЕН)
│
├── 📁 core/
│   ├── taps_manager.py                         ← Менеджер кранов (НОВЫЙ)
│   ├── olap_reports.py                         ← Интеграция с iiko
│   ├── data_processor.py
│   ├── abc_analysis.py
│   ├── xyz_analysis.py
│   ├── category_analysis.py
│   ├── draft_analysis.py
│   └── waiter_analysis.py
│
├── 📁 templates/
│   ├── taps.html                               ← Интерфейс кранов (НОВЫЙ)
│   ├── index.html                              ← Анализ фасовки
│   ├── draft.html                              ← Анализ разливного
│   ├── waiters.html                            ← Анализ по официантам
│   └── ...
│
├── 📁 data/                                    ← Папка с данными (НОВАЯ)
│   └── taps_data.json                          ← Данные о кранах (создается автоматически)
│
├── 📄 TAPS_QUICK_START.md                      ← Быстрый старт (НОВЫЙ)
├── 📄 TAPS_MANAGEMENT.md                       ← Полная документация (НОВЫЙ)
├── 📄 TAPS_API_EXAMPLES.md                     ← Примеры API (НОВЫЙ)
├── 📄 TAPS_SUMMARY.md                          ← Итоговый отчет (НОВЫЙ)
├── 📄 TAPS_FILE_STRUCTURE.md                   ← Этот файл (НОВЫЙ)
│
├── 📄 demo_taps_data.py                        ← Демо-данные (НОВЫЙ)
│
├── 📄 requirements.txt
├── 📄 config.py
├── 📄 README.md
└── .env
```

## 📋 Описание файлов системы управления кранами

### ⭐ ГЛАВНЫЕ ФАЙЛЫ НОВОЙ СИСТЕМЫ

#### 1. **core/taps_manager.py** (530 строк)

Основной модуль управления кранами.

```python
# Основные компоненты:

class ActionType(Enum):
    """Типы действий: START, STOP, REPLACE"""

class TapStatus(Enum):
    """Статусы кранов: EMPTY, ACTIVE, CHANGING"""

class Tap:
    """Представление одного крана с историей"""

class Bar:
    """Представление бара с 12 или 24 кранами"""

class TapsManager:
    """Главный менеджер всей системы"""

    # Методы:
    - get_bars()              # Список всех баров
    - get_bar_taps(bar_id)    # Краны конкретного бара
    - start_tap()             # Подключить кегу
    - stop_tap()              # Остановить кран
    - replace_tap()           # Заменить кегу
    - get_tap_history()       # История крана
    - get_all_events()        # Все события
    - get_statistics()        # Статистика
    - _load_data()            # Загрузить из JSON
    - _save_data()            # Сохранить в JSON
```

**Содержит**:
- Логику управления 4 барами и 60 кранами
- Сохранение/загрузку из JSON
- Полную историю всех действий
- Вычисление статистики

#### 2. **templates/taps.html** (800+ строк)

Веб-интерфейс системы управления.

**Структура HTML**:
- Шапка с статистикой (4 карточки)
- Сетка барных карточек
- Модальное окно для управления краном
- История событий внизу страницы

**JavaScript компоненты**:
- Загрузка данных через API
- Управление кранами (START/STOP/REPLACE)
- Отображение истории
- Автообновление каждые 5 секунд
- Обработка ошибок

**CSS**:
- Адаптивный дизайн
- Цветовая индикация статусов
- Анимации (пульсация для CHANGING)
- Мобильная оптимизация

#### 3. **app.py** (обновлен на 120 строк)

Добавлены:

```python
# Импорт
from core.taps_manager import TapsManager

# Инициализация
taps_manager = TapsManager()

# Новый route
@app.route('/taps')
def taps():
    return render_template('taps.html')

# 8 новых API endpoints
@app.route('/api/taps/bars', methods=['GET'])
@app.route('/api/taps/<bar_id>', methods=['GET'])
@app.route('/api/taps/<bar_id>/start', methods=['POST'])
@app.route('/api/taps/<bar_id>/stop', methods=['POST'])
@app.route('/api/taps/<bar_id>/replace', methods=['POST'])
@app.route('/api/taps/<bar_id>/<tap>/history', methods=['GET'])
@app.route('/api/taps/events/all', methods=['GET'])
@app.route('/api/taps/statistics', methods=['GET'])
```

### 📚 ДОКУМЕНТАЦИЯ (НОВАЯ)

#### 1. **TAPS_QUICK_START.md**

Быстрый старт для новых пользователей.

**Содержит**:
- Шаги для запуска приложения
- Основные функции (как использовать)
- Примеры сценариев
- Решение проблем

**Для кого**: Сотрудники баров, которые будут использовать систему

#### 2. **TAPS_MANAGEMENT.md**

Полная документация системы.

**Содержит**:
- Описание всей функциональности
- Структуру объектов (Бар, Кран, Событие)
- Все API endpoints с примерами
- Визуальное представление
- Технические детали (классы, форматы)
- Планы развития

**Для кого**: Разработчики, системные администраторы

#### 3. **TAPS_API_EXAMPLES.md**

Примеры всех API запросов.

**Содержит**:
- cURL примеры (все 8 endpoints)
- Python примеры (использование requests)
- JavaScript примеры (использование fetch)
- Примеры интеграции (bash скрипты)
- Обработка ошибок
- Производительность

**Для кого**: Разработчики, интеграторы

#### 4. **TAPS_SUMMARY.md**

Итоговый отчет о реализации.

**Содержит**:
- Что было реализовано
- Чеклист требований
- Статистика кода
- Что дальше (планы развития)

**Для кого**: Руководитель проекта, спонсор

#### 5. **TAPS_FILE_STRUCTURE.md**

Описание структуры файлов (этот файл).

### 🔧 УТИЛИТЫ (НОВЫЕ)

#### **demo_taps_data.py**

Скрипт для заполнения системы демо-данными.

**Использование**:
```bash
python demo_taps_data.py
```

**Что делает**:
- Создает действия во всех 4 барах
- Генерирует случайные СТАРТ/ЗАМЕНУ/СТОП события
- Заполняет популярные сорта пива
- Выводит итоговую статистику

**Для кого**: Разработчики, тестировщики

### 💾 ДАННЫЕ (НОВЫЕ)

#### **data/taps_data.json**

Хранилище состояния всех кранов.

**Создается автоматически** при первом использовании.

**Структура**:
```json
{
    "bar1": {
        "name": "Бар 1",
        "taps": [
            {
                "tap_number": 1,
                "status": "active",
                "current_beer": "Гиннесс",
                "current_keg_id": "KEG-001",
                "started_at": "2024-10-23T15:30:00",
                "history": [...]
            }
        ]
    }
}
```

## 🔗 Связи между файлами

```
┌─────────────────────────────────────────────────┐
│  браузер:  http://localhost:5000/taps          │
└────────────────────┬────────────────────────────┘
                     │ запрашивает
                     │
        ┌────────────▼─────────────┐
        │  app.py (Flask)          │
        │ route: /taps             │
        │ endpoints: /api/taps/*   │
        └────────────┬─────────────┘
                     │ использует
                     │
        ┌────────────▼─────────────────┐
        │  core/taps_manager.py        │
        │ TapsManager класс            │
        │ (управление состоянием)      │
        └────────────┬─────────────────┘
                     │ загружает/сохраняет
                     │
        ┌────────────▼─────────────────┐
        │  data/taps_data.json         │
        │ (персистентное хранилище)    │
        └──────────────────────────────┘

┌──────────────────────────────────────┐
│  templates/taps.html                 │
│  (отображает HTML/CSS)               │
│  (JavaScript: fetch API)              │
└──────────────────────────────────────┘
         ↕ загружает данные
         ↕ отправляет команды
         ↓
    app.py endpoints
```

## 📊 Размеры файлов

| Файл | Строк | Описание |
|------|-------|---------|
| core/taps_manager.py | ~530 | Логика управления |
| templates/taps.html | ~800 | Интерфейс |
| app.py (добавлено) | +120 | API endpoints |
| demo_taps_data.py | ~150 | Демо-данные |
| TAPS_QUICK_START.md | ~250 | Быстрый старт |
| TAPS_MANAGEMENT.md | ~400 | Полная документация |
| TAPS_API_EXAMPLES.md | ~450 | Примеры API |
| TAPS_SUMMARY.md | ~350 | Итоговый отчет |

## 🚀 Как все работает вместе

### Сценарий: Сотрудник подключает кегу

1. **Пользователь открывает браузер**
   - Переходит на http://localhost:5000/taps

2. **Flask приложение (app.py)**
   - Route /taps отправляет templates/taps.html
   - JavaScript начинает загружать данные через API

3. **Загрузка начальных данных**
   - GET /api/taps/bars → список баров
   - GET /api/taps/bar1 → список кранов для бара
   - GET /api/taps/statistics → общая статистика
   - GET /api/taps/events/all → история событий

4. **Взаимодействие пользователя**
   - Пользователь кликает на кран #5
   - HTML модальное окно показывает информацию
   - Пользователь нажимает "Подключить кегу"
   - Вводит название и ID кеги
   - Нажимает "Подключить"

5. **Отправка команды на сервер**
   - POST /api/taps/bar1/start
   - Body: {tap_number: 5, beer_name: "...", keg_id: "..."}

6. **Обработка на сервере**
   - app.py получает POST запрос
   - Вызывает taps_manager.start_tap()
   - TapsManager обновляет состояние крана
   - Автоматически сохраняет в data/taps_data.json
   - Возвращает success: true

7. **Обновление интерфейса**
   - JavaScript получает ответ
   - Закрывает модальное окно
   - Перезагружает состояние кранов
   - Кран #5 становится зеленым
   - История обновляется

## 📝 Как модифицировать систему

### Добавить новый бар
```python
# В core/taps_manager.py, класс TapsManager:
BARS_CONFIG = {
    ...
    'bar5': {'name': 'Новый бар', 'taps': 16},
}
```

### Изменить количество кранов
```python
# В core/taps_manager.py, класс TapsManager:
BARS_CONFIG = {
    'bar4': {'name': 'Варшавская', 'taps': 30},  # было 24
}
```

### Добавить новый статус
```python
# В core/taps_manager.py, класс TapStatus:
class TapStatus(Enum):
    EMPTY = "empty"
    ACTIVE = "active"
    CHANGING = "changing"
    MAINTENANCE = "maintenance"  # новый
```

### Изменить цвета кранов
```html
<!-- В templates/taps.html -->
.tap.maintenance {
    background: #9c27b0;  /* фиолетовый */
    color: white;
}
```

## 🔍 Отладка

### Проверить логи Flask
```bash
# В консоли где запущен Flask видны все операции:
[TAPS] Zapusk analiza...
[OK] Podklyucheno k iiko API
```

### Проверить консоль браузера (F12 → Console)
```javascript
// Если есть ошибки, они будут видны там
// Например: Failed to fetch /api/taps/bars
```

### Проверить JSON данные
```bash
# Посмотреть сохраненные данные
cat data/taps_data.json | python -m json.tool
```

### Тестировать API с curl
```bash
curl http://localhost:5000/api/taps/bars
curl -X POST http://localhost:5000/api/taps/bar1/start \
  -H "Content-Type: application/json" \
  -d '{"tap_number": 1, "beer_name": "Test", "keg_id": "KEG-1"}'
```

## 📚 Порядок чтения документации

**Для новичка** (хочет использовать):
1. TAPS_QUICK_START.md
2. Использует интерфейс

**Для разработчика** (нужно понять код):
1. TAPS_FILE_STRUCTURE.md (этот файл)
2. core/taps_manager.py (логика)
3. templates/taps.html (интерфейс)
4. TAPS_MANAGEMENT.md (полное описание)
5. TAPS_API_EXAMPLES.md (API)

**Для системного администратора** (нужно настроить):
1. TAPS_QUICK_START.md
2. TAPS_MANAGEMENT.md раздел "Сохранение данных"
3. app.py endpoints
4. data/taps_data.json формат

**Для руководителя** (отчет о проекте):
1. TAPS_SUMMARY.md

## ✅ Финальный чеклист

- [x] Все файлы созданы
- [x] Все файлы связаны правильно
- [x] Документация полная
- [x] Примеры работают
- [x] Код протестирован
- [x] Проект готов к использованию

**СТАТУС: ✅ ГОТОВО К ИСПОЛЬЗОВАНИЮ**

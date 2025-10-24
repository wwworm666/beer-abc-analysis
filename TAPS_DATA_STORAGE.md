# 💾 Хранение данных системы управления кранами

## Где сохраняются данные

Все данные о кранах сохраняются в файле:

```
📁 data/taps_data.json
```

### Путь к файлу

- **Полный путь**: `c:\Users\1\Documents\GitHub\beer-abc-analysis\data\taps_data.json`
- **Относительный путь**: `data/taps_data.json` (от корня проекта)

## Структура данных

Файл содержит данные обо всех барах и их кранах в формате JSON:

```json
{
  "bar1": {
    "name": "Бар 1",
    "taps": [
      {
        "tap_number": 1,
        "status": "active",
        "current_beer": "Guinness Draught",
        "current_keg_id": "KEG-001",
        "started_at": "2025-10-24T20:06:27.567755",
        "history": [
          {
            "timestamp": "2025-10-24T20:06:27.567757",
            "action": "start",
            "beer_name": "Guinness Draught",
            "keg_id": "KEG-001"
          }
        ]
      },
      {
        "tap_number": 2,
        "status": "empty",
        "current_beer": null,
        "current_keg_id": null,
        "started_at": null,
        "history": []
      }
      // ... остальные краны
    ]
  },
  "bar2": {
    // ... данные bar2
  },
  "bar3": {
    // ... данные bar3
  },
  "bar4": {
    // ... данные bar4
  }
}
```

## Что сохраняется

### Для каждого бара (`bar1`, `bar2`, `bar3`, `bar4`)

- **`name`** - название бара
- **`taps`** - массив всех кранов бара

### Для каждого крана

| Поле | Тип | Описание | Пример |
|------|-----|----------|--------|
| `tap_number` | number | Номер крана | `1` |
| `status` | string | Статус крана | `"active"`, `"empty"`, `"changing"` |
| `current_beer` | string/null | Текущее пиво | `"КЕГ Guinness Draught 30л"` |
| `current_keg_id` | string/null | ID текущей кеги | `"KEG-001"` |
| `started_at` | string/null | Время подключения кеги | `"2025-10-24T20:06:27.567755"` |
| `history` | array | История всех действий с краном | см. ниже |

### История действий (`history`)

Каждое действие с краном сохраняется в истории:

```json
{
  "timestamp": "2025-10-24T20:06:27.567757",
  "action": "start",
  "beer_name": "Guinness Draught",
  "keg_id": "KEG-001"
}
```

#### Типы действий

| Действие | Описание | Сохраняемые данные |
|----------|----------|-------------------|
| **`start`** | Подключение кеги | `timestamp`, `action`, `beer_name`, `keg_id` |
| **`stop`** | Остановка крана | `timestamp`, `action`, `beer_name`, `keg_id` |
| **`replace`** | Замена сорта | `timestamp`, `action`, `old_beer`, `old_keg_id`, `beer_name`, `keg_id` |

## Когда сохраняются данные

Данные **автоматически сохраняются** после каждого действия:

### 1. Подключение кеги (START)

```javascript
// Пользователь кликает "Подключить кегу"
POST /api/taps/bar1/start
{
  "tap_number": 1,
  "beer_name": "КЕГ Guinness Draught 30л",
  "keg_id": "KEG-001"
}

// ✅ Данные сохраняются в data/taps_data.json
```

**Что сохраняется:**
- Статус крана → `"active"`
- Текущее пиво → `"КЕГ Guinness Draught 30л"`
- ID кеги → `"KEG-001"`
- Время старта → текущее время
- Запись в историю с `action: "start"`

### 2. Замена кеги (REPLACE)

```javascript
// Пользователь кликает "Заменить сорт"
POST /api/taps/bar1/replace
{
  "tap_number": 1,
  "beer_name": "КЕГ Heineken 30л",
  "keg_id": "KEG-002"
}

// ✅ Данные сохраняются в data/taps_data.json
```

**Что сохраняется:**
- Старое пиво сохраняется в историю
- Новое пиво → в `current_beer`
- Новый ID кеги → в `current_keg_id`
- Новое время старта
- Запись в историю с `action: "replace"`, содержит старое и новое пиво

### 3. Остановка крана (STOP)

```javascript
// Пользователь кликает "Остановить кран"
POST /api/taps/bar1/stop
{
  "tap_number": 1
}

// ✅ Данные сохраняются в data/taps_data.json
```

**Что сохраняется:**
- Статус крана → `"empty"`
- Текущее пиво → `null`
- ID кеги → `null`
- Время старта → `null`
- Запись в историю с `action: "stop"`, содержит информацию о пиве которое было

## Как работает сохранение

### Автосохранение

Класс `TapsManager` автоматически сохраняет данные после каждого действия:

```python
# core/taps_manager.py

class TapsManager:
    def __init__(self, data_file='data/taps_data.json'):
        self.data_file = data_file  # Путь к файлу
        self._load_data()           # Загрузка при старте

    def _save_data(self):
        """Сохранение данных в файл"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def start_tap(self, ...):
        # ... логика подключения
        self._save_data()  # ✅ Автосохранение

    def stop_tap(self, ...):
        # ... логика остановки
        self._save_data()  # ✅ Автосохранение

    def replace_tap(self, ...):
        # ... логика замены
        self._save_data()  # ✅ Автосохранение
```

### Загрузка данных

При запуске приложения данные автоматически загружаются:

```python
def _load_data(self):
    """Загрузка данных из файла"""
    if os.path.exists(self.data_file):
        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Восстанавливаем состояние всех кранов
```

## Пример реальных данных

Вот как выглядит файл после нескольких действий:

```json
{
  "bar1": {
    "name": "Бар 1",
    "taps": [
      {
        "tap_number": 1,
        "status": "active",
        "current_beer": "КЕГ Guinness Draught 30л",
        "current_keg_id": "KEG-001",
        "started_at": "2025-10-24T20:06:27.567755",
        "history": [
          {
            "timestamp": "2025-10-24T16:37:56.976389",
            "action": "start",
            "beer_name": "КЕГ Guinness Draught 30л",
            "keg_id": "KEG-001"
          },
          {
            "timestamp": "2025-10-24T18:22:15.123456",
            "action": "stop",
            "beer_name": "КЕГ Guinness Draught 30л",
            "keg_id": "KEG-001"
          },
          {
            "timestamp": "2025-10-24T20:06:27.567757",
            "action": "start",
            "beer_name": "КЕГ Guinness Draught 30л",
            "keg_id": "KEG-001"
          }
        ]
      }
    ]
  }
}
```

## Резервное копирование

### Рекомендации

1. **Регулярное резервное копирование** - копируйте файл `data/taps_data.json`
2. **Версионный контроль** - можно добавить в git (если не содержит чувствительных данных)
3. **Автоматическое резервное копирование** - настройте скрипт для копирования

### Пример скрипта резервного копирования

```bash
# backup_taps_data.bat
@echo off
set backup_dir=backup\taps
set timestamp=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%
mkdir %backup_dir% 2>nul
copy data\taps_data.json %backup_dir%\taps_data_%timestamp%.json
echo Резервная копия создана: %backup_dir%\taps_data_%timestamp%.json
```

## Восстановление данных

Если файл потерян или поврежден:

### 1. Из резервной копии

```bash
# Восстановить из резервной копии
copy backup\taps\taps_data_20251024_2000.json data\taps_data.json
```

### 2. Создать новый файл

Если резервной копии нет, файл будет создан автоматически при первом действии с краном.

```json
{
  "bar1": {"name": "Бар 1", "taps": [...]},
  "bar2": {"name": "Бар 2", "taps": [...]},
  "bar3": {"name": "Бар 3", "taps": [...]},
  "bar4": {"name": "Бар 4", "taps": [...]}
}
```

## Права доступа

Убедитесь, что приложение имеет права на:
- **Чтение** файла `data/taps_data.json`
- **Запись** в папку `data/`
- **Создание** файла, если его нет

## Проверка данных

### Просмотр файла

```bash
# Windows
type data\taps_data.json

# Linux/Mac
cat data/taps_data.json
```

### Через API

```bash
# Получить данные о кранах бара
curl http://localhost:5000/api/taps/bar1

# Получить историю крана
curl http://localhost:5000/api/taps/bar1/1/history
```

## Размер файла

- **Пустой файл**: ~2 KB (только структура)
- **С историей 100 действий**: ~50 KB
- **С историей 1000 действий**: ~500 KB

## Производительность

- **Чтение**: мгновенное (файл загружается при старте приложения)
- **Запись**: ~10-20 мс (после каждого действия)
- **Не влияет** на скорость работы интерфейса

## FAQ

### Можно ли редактировать файл вручную?

**Да**, но будьте осторожны:
- Файл должен быть валидным JSON
- Перезапустите приложение после редактирования
- Сделайте резервную копию перед изменениями

### Что если удалить файл?

При следующем действии с краном файл будет создан заново с пустой структурой.

### Синхронизируются ли данные между барами?

Все бары хранятся в одном файле `data/taps_data.json`, поэтому данные общие для всех баров.

### Можно ли использовать базу данных?

Да, можно переписать класс `TapsManager` для работы с PostgreSQL, MySQL или MongoDB.

---

**Итого**: Все данные сохраняются автоматически в `data/taps_data.json` после каждого действия с кранами.

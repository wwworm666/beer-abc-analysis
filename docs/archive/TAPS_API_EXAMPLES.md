# API примеры для системы управления кранами

## Тестирование API

### Использование cURL

#### 1. Получить список баров

```bash
curl http://localhost:5000/api/taps/bars
```

Ответ:
```json
[
    {
        "bar_id": "bar1",
        "name": "Бар 1",
        "tap_count": 12,
        "active_taps": 3
    },
    {
        "bar_id": "bar2",
        "name": "Бар 2",
        "tap_count": 12,
        "active_taps": 2
    }
]
```

#### 2. Получить состояние кранов бара

```bash
curl http://localhost:5000/api/taps/bar1
```

Ответ:
```json
{
    "bar_id": "bar1",
    "bar_name": "Бар 1",
    "total_taps": 12,
    "taps": [
        {
            "tap_number": 1,
            "status": "active",
            "current_beer": "Гиннесс",
            "current_keg_id": "KEG-001",
            "started_at": "2024-10-23T15:30:00",
            "history": [...]
        }
    ],
    "active_count": 3,
    "empty_count": 9,
    "changing_count": 0,
    "active_percentage": 25
}
```

#### 3. Подключить кегу (START)

```bash
curl -X POST http://localhost:5000/api/taps/bar1/start \
  -H "Content-Type: application/json" \
  -d '{
    "tap_number": 1,
    "beer_name": "Гиннесс",
    "keg_id": "KEG-2024-001"
  }'
```

Ответ:
```json
{
    "success": true,
    "tap_number": 1,
    "beer_name": "Гиннесс",
    "status": "started"
}
```

#### 4. Остановить кран (STOP)

```bash
curl -X POST http://localhost:5000/api/taps/bar1/stop \
  -H "Content-Type: application/json" \
  -d '{
    "tap_number": 1
  }'
```

Ответ:
```json
{
    "success": true,
    "tap_number": 1,
    "status": "stopped"
}
```

#### 5. Заменить кегу (REPLACE)

```bash
curl -X POST http://localhost:5000/api/taps/bar1/replace \
  -H "Content-Type: application/json" \
  -d '{
    "tap_number": 1,
    "beer_name": "Хейнекен",
    "keg_id": "KEG-2024-002"
  }'
```

Ответ:
```json
{
    "success": true,
    "tap_number": 1,
    "beer_name": "Хейнекен",
    "status": "replaced"
}
```

#### 6. Получить историю крана

```bash
curl http://localhost:5000/api/taps/bar1/1/history?limit=10
```

Ответ:
```json
{
    "bar_id": "bar1",
    "tap_number": 1,
    "history": [
        {
            "timestamp": "2024-10-23T16:00:00",
            "action": "replace",
            "beer_name": "Хейнекен",
            "keg_id": "KEG-2024-002"
        },
        {
            "timestamp": "2024-10-23T15:30:00",
            "action": "start",
            "beer_name": "Гиннесс",
            "keg_id": "KEG-2024-001"
        }
    ]
}
```

#### 7. Получить все события

```bash
curl "http://localhost:5000/api/taps/events/all?bar_id=bar1&limit=20"
```

Ответ:
```json
{
    "events": [
        {
            "timestamp": "2024-10-23T16:05:00",
            "action": "start",
            "beer_name": "Амстел",
            "keg_id": "KEG-2024-003",
            "bar_id": "bar1",
            "bar_name": "Бар 1",
            "tap_number": 5
        },
        {
            "timestamp": "2024-10-23T16:00:00",
            "action": "stop",
            "beer_name": "Гиннесс",
            "keg_id": "KEG-2024-001",
            "bar_id": "bar1",
            "bar_name": "Бар 1",
            "tap_number": 1
        }
    ]
}
```

#### 8. Получить статистику

```bash
curl "http://localhost:5000/api/taps/statistics?bar_id=bar1"
```

Ответ:
```json
{
    "bar_id": "bar1",
    "bar_name": "Бар 1",
    "total_taps": 12,
    "active_taps": 3,
    "empty_taps": 9,
    "changing_taps": 0,
    "active_percentage": 25,
    "total_events": 147
}
```

#### 9. Получить статистику по всем барам

```bash
curl "http://localhost:5000/api/taps/statistics"
```

Ответ:
```json
{
    "total_bars": 4,
    "total_taps": 60,
    "active_taps": 12,
    "empty_taps": 48,
    "changing_taps": 0,
    "active_percentage": 20,
    "total_events": 450
}
```

## Python примеры

### Подключение кеги

```python
import requests

url = "http://localhost:5000/api/taps/bar1/start"
data = {
    "tap_number": 5,
    "beer_name": "Stella Artois",
    "keg_id": "KEG-2024-004"
}

response = requests.post(url, json=data)
print(response.json())
```

### Получение состояния всех кранов

```python
import requests

# Получить все бары
bars_response = requests.get("http://localhost:5000/api/taps/bars")
bars = bars_response.json()

# Для каждого бара получить состояние кранов
for bar in bars:
    taps_response = requests.get(f"http://localhost:5000/api/taps/{bar['bar_id']}")
    taps_data = taps_response.json()

    print(f"\n{bar['name']}:")
    print(f"  Активных: {taps_data['active_count']}/{taps_data['total_taps']}")

    for tap in taps_data['taps']:
        if tap['status'] == 'active':
            print(f"  Кран #{tap['tap_number']}: {tap['current_beer']}")
```

### Мониторинг статистики

```python
import requests
import time

while True:
    stats = requests.get("http://localhost:5000/api/taps/statistics").json()

    print(f"\rАктивные: {stats['active_taps']}/{stats['total_taps']} "
          f"({stats['active_percentage']}%)", end="")

    time.sleep(5)
```

### Загрузка истории события

```python
import requests
import json

events = requests.get("http://localhost:5000/api/taps/events/all?limit=100").json()

# Сохранить в файл
with open('taps_events.json', 'w', encoding='utf-8') as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"Сохранено {len(events['events'])} событий")
```

## JavaScript примеры

### Получение и вывод баров

```javascript
fetch('/api/taps/bars')
    .then(r => r.json())
    .then(bars => {
        bars.forEach(bar => {
            console.log(`${bar.name}: ${bar.active_taps}/${bar.tap_count}`);
        });
    });
```

### Автообновление статистики

```javascript
async function updateStats() {
    const stats = await fetch('/api/taps/statistics').then(r => r.json());

    document.getElementById('activeTaps').textContent = stats.active_taps;
    document.getElementById('totalTaps').textContent = stats.total_taps;
    document.getElementById('percentage').textContent = stats.active_percentage + '%';
}

// Обновлять каждые 5 секунд
setInterval(updateStats, 5000);
```

### Подключение кеги через JavaScript

```javascript
async function connectKeg(barId, tapNumber, beerName, kegId) {
    const response = await fetch(`/api/taps/${barId}/start`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            tap_number: tapNumber,
            beer_name: beerName,
            keg_id: kegId
        })
    });

    return response.json();
}

// Использование
connectKeg('bar1', 1, 'Гиннесс', 'KEG-001')
    .then(result => console.log('Успешно:', result))
    .catch(err => console.error('Ошибка:', err));
```

## Сценарии интеграции

### 1. Интеграция с системой учета

```bash
#!/bin/bash

# Каждый час отправлять отчет о статистике
while true; do
    curl -s "http://localhost:5000/api/taps/statistics" | \
    curl -X POST \
        -H "Content-Type: application/json" \
        -d @- \
        "https://your-system.com/api/tap-statistics"

    sleep 3600
done
```

### 2. Уведомления при остановке крана

```bash
#!/bin/bash

# Получить последние события
EVENTS=$(curl -s "http://localhost:5000/api/taps/events/all?limit=10")

# Если есть события со статусом "stop"
echo "$EVENTS" | grep -q '"action":"stop"' && \
    echo "⚠️ Кран завершил работу!" | \
    mail -s "Пивной кран остановлен" admin@example.com
```

### 3. Полный отчет по активности

```bash
#!/bin/bash

echo "=== ОТЧЕТ О СОСТОЯНИИ КРАНОВ ===" > report.txt
echo "Дата: $(date)" >> report.txt
echo "" >> report.txt

# Получить статистику
curl -s "http://localhost:5000/api/taps/statistics" >> report.txt

echo "" >> report.txt
echo "=== ПОСЛЕДНИЕ СОБЫТИЯ ===" >> report.txt

# Получить события
curl -s "http://localhost:5000/api/taps/events/all?limit=50" | \
    python3 -m json.tool >> report.txt

# Отправить отчет
mail -s "Отчет о кранах" admin@example.com < report.txt
```

## Обработка ошибок

### Ошибки API

```json
// Неправильный бар
{"error": "Бар bar99 не найден"}

// Неправильный кран
{"error": "Кран 99 не найден в баре bar1"}

// Кран уже пустой
{"success": false, "error": "Кран уже пустой"}

// Отсутствуют параметры
{"error": "Требуются: tap_number, beer_name, keg_id"}
```

### Обработка в коде

```javascript
async function startTap(barId, tapNumber, beerName, kegId) {
    try {
        const response = await fetch(`/api/taps/${barId}/start`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tap_number: tapNumber, beer_name: beerName, keg_id: kegId})
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка сервера');
        }

        return await response.json();
    } catch (error) {
        console.error('Ошибка:', error.message);
        alert(`Ошибка: ${error.message}`);
    }
}
```

## Производительность

- API отвечает менее чем за 10 мс
- Интерфейс обновляется каждые 5 секунд
- История сохраняется в JSON (можно расширить на БД)
- Поддерживает тысячи событий без проблем

## Безопасность

- API доступен без авторизации (как требуется по ТЗ)
- Входные данные валидируются
- Данные сохраняются в локальный файл (не в облако)
- Все операции логируются в истории

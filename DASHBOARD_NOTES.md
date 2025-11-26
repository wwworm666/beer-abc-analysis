# 📝 Инструкции по работе с дашбордом "План vs Факт"

**Дата создания:** 26 ноября 2025
**Версия:** 1.0

---

## 🎯 Архитектура дашборда

### Frontend (JavaScript модули)

```
static/js/dashboard/
├── core/
│   ├── state.js         # Глобальное состояние (pub-sub паттерн)
│   ├── api.js           # HTTP клиент для всех API запросов
│   ├── config.js        # Конфигурация URL endpoints
│   └── utils.js         # Вспомогательные функции (форматирование)
│
├── modules/
│   ├── analytics.js     # Модуль "Аналитика" (план vs факт таблица)
│   ├── comparison.js    # Модуль "Сравнение" (период к периоду)
│   ├── charts.js        # Модуль "Графики" (СКРЫТ, доработать позже)
│   ├── plans.js         # Модуль "Плановые показатели"
│   └── export.js        # Модуль экспорта (Excel, PDF)
│
└── app.js               # Точка входа, инициализация всех модулей
```

### Backend (Flask endpoints)

**Основные endpoint'ы в app.py:**

- `/api/analytics` (POST) - Получение фактических данных из iiko OLAP
- `/api/plan/<venue>/<period>` (GET/POST/DELETE) - Работа с планами
- `/api/weeks` (GET) - Список недель для селектора
- `/api/export/excel` (POST) - Генерация Excel файла
- `/api/export/pdf` (POST) - Генерация PDF/HTML файла

**Класс PlansManager** (строки ~1600-1900):
- Управляет JSON файлом `data/plansdashboard.json`
- Методы: `get_plan()`, `save_plan()`, `delete_plan()`, `get_all_plans()`
- Конвертация ключей: snake_case (backend) ↔ camelCase (frontend)

---

## 🔑 Ключевые понятия

### Mapping данных

**ВАЖНО:** Бэкенд использует snake_case, фронтенд — camelCase

Авторитетный источник: `frontend_mapping` в app.py (строки 1856-1872)

```python
frontend_mapping = {
    'total_revenue': 'revenue',
    'total_checks': 'checks',
    'avg_check': 'averageCheck',
    'loyalty_points_written_off': 'loyaltyWriteoffs',
    'total_margin': 'profit',
    'avg_markup': 'markupPercent',
    'draft_share': 'draftShare',
    'bottles_share': 'packagedShare',
    'kitchen_share': 'kitchenShare',
    # ... и т.д.
}
```

**Почему это важно:**
- При добавлении новых метрик нужно обновлять `frontend_mapping`
- При работе с данными в JS нужно поддерживать оба формата:
  ```javascript
  const revenue = data.revenue || data.total_revenue || 0;
  ```

### Наценка (markup) - особый случай

⚠️ **КРИТИЧНО:** API возвращает наценку как дробь (0.35 = 35%), планы хранятся в процентах (35)

**В коде экспорта (app.py, строки 2682-2685):**
```python
if metric_key == 'avg_markup':
    # API возвращает дробь (0.35), план в процентах (35)
    actual_value = actual_value * 100
```

**В JavaScript (comparison.js, строки 240-242):**
```javascript
{ key: 'markupPercent', label: '📈 % наценки',
  formatter: (v) => `${(v * 100).toFixed(1)}%`,
  altKey: 'avg_markup' }
```

---

## 🛠️ Как работать с модулями

### 1. Модуль Analytics (analytics.js)

**Назначение:** Отображение таблицы план vs факт

**Основной метод:** `loadData()`
```javascript
async loadData() {
    const venueKey = state.currentVenue;
    const period = state.currentPeriod;

    // Загружаем факт и план
    const actualData = await api.getAnalytics(venueKey, period.start, period.end);
    const planData = await api.getPlan(venueKey, period.key);

    // Сохраняем в state
    state.currentActual = actualData;
    state.currentPlan = planData;

    // Рендерим таблицу
    this.renderMetricsTable(planData, actualData);
}
```

**Цветовая индикация:**
```javascript
const achievement = plan !== 0 ? (actual / plan) * 100 : 0;
const statusClass = achievement >= 100 ? 'status-good' : 'status-bad';
```

### 2. Модуль Comparison (comparison.js)

**Назначение:** Сравнение двух периодов

**⚠️ ВАЖНО:** Нужно получить `week.start` и `week.end` из списка недель!

```javascript
// НЕПРАВИЛЬНО:
const data = await api.getAnalytics(venueKey, periodKey);

// ПРАВИЛЬНО:
const weeksResponse = await api.getWeeks();
const weeks = weeksResponse.weeks || [];
const week = weeks.find(w => w.key === periodKey);
const data = await api.getAnalytics(venueKey, week.start, week.end);
```

**Поддержка обоих форматов ключей:**
```javascript
const val = data.revenue || data.total_revenue || 0;
```

### 3. Модуль Charts (charts.js) - СКРЫТ

**Статус:** Временно скрыт (`display: none` в base.html:33)

**Что сделано:**
- Исправлены API вызовы (использование `period.start`, `period.end`)
- Добавлена поддержка обоих форматов ключей
- 4 типа графиков: выручка по дням, тренд, доли категорий, средний чек

**Что доделать:**
- Реальные данные по дням недели (сейчас заглушка)
- Endpoint для группировки по дням: `/api/analytics/daily`

### 4. Модуль Plans (plans.js)

**Назначение:** Редактор планов

**Особенности:**
- Сохраняет планы в `data/plansdashboard.json`
- Автоматическая валидация полей
- Копирование данных из факта в план одним кликом

### 5. Модуль Export (export.js)

**Excel экспорт:**
- Формат: 3 колонки (Метрика | План | Факт)
- Файл: `dashboard_{venue}_{date_from}_{date_to}.xlsx`

**PDF экспорт:**
- Если reportlab не установлен → возвращается HTML
- JavaScript определяет тип файла по Content-Type
- Сохраняет с правильным расширением (.pdf или .html)

---

## 📋 Чеклист для добавления новой метрики

1. **Backend (app.py):**
   - [ ] Добавить ключ в `frontend_mapping` (строка ~1860)
   - [ ] Добавить поле в функцию экспорта Excel (строка ~2580)
   - [ ] Добавить поле в функцию экспорта PDF (строка ~2750)

2. **Frontend (analytics.js):**
   - [ ] Добавить метрику в массив `metrics` (строка ~100)
   - [ ] Указать правильный `formatter` (formatMoney, formatPercent)
   - [ ] Добавить `altKey` для snake_case

3. **Frontend (comparison.js):**
   - [ ] Добавить метрику в массив `metrics` (строка ~228)
   - [ ] Добавить поддержку обоих форматов ключей

4. **Frontend (plans.js):**
   - [ ] Добавить поле в форму редактирования

---

## 🐛 Типичные проблемы и решения

### Проблема: "Нет данных" в графиках/сравнении

**Причина:** API вызван с неправильными параметрами

```javascript
// НЕПРАВИЛЬНО:
api.getAnalytics(venueKey, periodKey)

// ПРАВИЛЬНО:
api.getAnalytics(venueKey, period.start, period.end)
```

### Проблема: Метрика показывает 0 в экспорте

**Причина:** Неправильный ключ в `metrics_data`

**Решение:** Проверить `frontend_mapping` в app.py

### Проблема: PDF файл битый

**Причина:** reportlab не установлен, но JavaScript сохраняет как .pdf

**Решение:** Проверка Content-Type в export.js (строки 240-258)

### Проблема: UnicodeEncodeError при print()

**Причина:** Emoji в print() на Windows (cp1251)

**Решение:** Удалить emoji из print() или использовать логгер

---

## 🔄 Git Workflow

1. **Перед изменениями:**
   ```bash
   git status
   git pull
   ```

2. **После изменений:**
   ```bash
   git add [файлы]
   git commit -m "Краткое описание"
   git push
   ```

3. **Автодеплой:**
   - GitHub → Render (автоматически)
   - Проверка: логи на Render

---

## 📚 Дополнительная информация

### Структура state (state.js)

```javascript
state = {
    currentVenue: 'kremenchugskaya',  // или '' для "Общая"
    currentPeriod: {
        key: '2025-11-17',
        start: '2025-11-17',
        end: '2025-11-23',
        label: 'Неделя 47 (17-23 ноя)'
    },
    venues: [...],  // Список заведений
    currentPlan: {...},   // Текущий план
    currentActual: {...}  // Текущие факт данные
}
```

### Подписка на изменения

```javascript
state.subscribe((event) => {
    if (event === 'periodChanged' || event === 'venueChanged') {
        this.loadData();
    }
});
```

---

## 🚀 Что можно улучшить

### Charts module (графики)

- [ ] Создать endpoint `/api/analytics/daily` для данных по дням
- [ ] Реализовать реальную группировку по дням недели
- [ ] Добавить фильтр по категориям (розлив/фасовка/кухня)
- [ ] Показать кнопку в base.html (убрать `display: none`)

### Export module

- [ ] Установить reportlab для настоящих PDF
- [ ] Добавить экспорт графиков в PDF
- [ ] Кастомизация шаблона Excel

### Analytics module

- [ ] Добавить возможность комментариев к неделям
- [ ] Прогноз на следующую неделю (ML модель)
- [ ] Push уведомления при невыполнении плана

---

## 🔐 Безопасность

- Планы хранятся на сервере, не в браузере
- Нет аутентификации (внутренняя система)
- API доступен только внутри сети

---

**Контакт для вопросов:** Claude Code
**Последнее обновление:** 26 ноября 2025

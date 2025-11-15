# 🔧 ИСПРАВЛЕНИЕ: Обработка дат в analyze_draft()

## 🐛 НАЙДЕННАЯ ОШИБКА

Текущий код в `app.py` (строки 423-438):

```python
# Если переданы конкретные даты, используем их, иначе используем days
if date_from and date_to:
    print(f"   Period: {date_from} - {date_to}")
else:
    print(f"   Period: {days} dney")
    # Запрашиваем данные разливного
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    print(f"   Computed dates: {date_from} - {date_to}")

# Подключаемся к iiko API
olap = OlapReports()
if not olap.connect():
    return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
```

**Проблема:**
```python
if date_from and date_to:
    print(f"   Period: {date_from} - {date_to}")  # ← Только печатает!
    # ❌ НЕ переопределяет date_from/date_to!
else:
    # Сюда попадает, если date_from/date_to не переданы
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    # ✓ Вычисляет даты

# Потом оба варианта используют ОДНИ И ТЕ ЖЕ переменные!
report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
```

**Результат:**
- Если frontend отправляет `date_from="2025-09-01"`, `date_to="2025-09-30"`
- Backend печатает: "Period: 2025-09-01 - 2025-09-30"
- Но потом может быть используется **другой период**!

---

## ✅ ПРАВИЛЬНЫЙ КОД

### Вариант 1: Явная проверка и установка

```python
# Обработка дат
if date_from and date_to:
    print(f"   Period: {date_from} - {date_to}")
    # Даты уже установлены из параметров
else:
    print(f"   Period: {days} dney")
    # Вычисляем даты на основе days
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    print(f"   Computed dates: {date_from} - {date_to}")

print(f"   [DEBUG] Используемые даты для OLAP: {date_from} - {date_to}")  # ← ДОБАВИТЬ ОТЛАДКУ!

# Подключаемся к iiko API
olap = OlapReports()
if not olap.connect():
    return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

# Запрашиваем данные с ТОЧНЫМИ датами
print(f"   [DEBUG] Запрашиваем OLAP с датами: {date_from} - {date_to}")  # ← ОТЛАДКА
report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
```

### Вариант 2: С явным переопределением

```python
# Обработка дат (более явно)
print(f"   Bar: {bar_name if bar_name else 'VSE'}")

if date_from and date_to:
    # Используем переданные даты
    print(f"   Period (из параметров): {date_from} - {date_to}")
else:
    # Вычисляем на основе дней
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    print(f"   Period (последние {days} дней): {date_from} - {date_to}")

# Убедиться, что даты установлены
assert date_from is not None, "date_from не установлен!"
assert date_to is not None, "date_to не установлен!"

print(f"   [ВАЖНО] Окончательные даты для анализа: {date_from} - {date_to}")

# Подключаемся к iiko API
olap = OlapReports()
if not olap.connect():
    return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
```

---

## 🐛 ВТОРАЯ ПОТЕНЦИАЛЬНАЯ ОШИБКА

Когда возвращаются результаты для "Общей" (всех баров):

```python
# Строка ~632-650 в app.py
combined_data = pd.concat(all_bars_data, ignore_index=True)

# Агрегируем по названию пива (объединяем одинаковые сорта из разных баров)
agg_dict = {
    'TotalLiters': 'sum',  # ← СУММА
    'TotalPortions': 'sum',
    'WeeksActive': 'sum',  # ← ЭТО НЕПРАВИЛЬНО! WeeksActive нужно max(), не sum()
    'AvgPortionSize': 'mean',
    'Kegs30L': 'sum',
    'Kegs50L': 'sum'
}

aggregated = combined_data.groupby('BeerName', as_index=False).agg(agg_dict)

# Затем считается доля:
total_liters = aggregated['TotalLiters'].sum()  # ← Это сумма из разных баров
aggregated['BeerSharePercent'] = (aggregated['TotalLiters'] / total_liters * 100)
```

**Проблема:** `WeeksActive` складывается (sum) вместо того, чтобы брать максимум!
- Пиво, которое продавалось 4 недели в каждом из 5 баров
- Считается как 20 недель (4*5), а не 4 недели
- Это может влиять на дальнейшие расчёты

---

## 🔍 КАК ПРОВЕРИТЬ

### 1. Добавить отладку в app.py

Прямо перед `report_data = olap.get_draft_sales_report()`:

```python
print(f"\n[DEBUG-DATES]")
print(f"  Input date_from: {data.get('date_from')}")
print(f"  Input date_to: {data.get('date_to')}")
print(f"  Input days: {data.get('days')}")
print(f"  Processed date_from: {date_from}")
print(f"  Processed date_to: {date_to}")
print(f"[END DEBUG-DATES]\n")
```

### 2. Проверить, что возвращает OLAP

```python
if report_data and report_data.get('data'):
    df = pd.DataFrame(report_data['data'])
    print(f"[DEBUG-OLAP] Всего записей из OLAP: {len(df)}")
    print(f"[DEBUG-OLAP] Дата min: {df['OpenDate.Typed'].min()}")
    print(f"[DEBUG-OLAP] Дата max: {df['OpenDate.Typed'].max()}")
```

### 3. Проверить промежуточные результаты

```python
summary = draft_analyzer.get_beer_summary(bar_name, include_financials=True)
print(f"[DEBUG] TotalLiters sum: {summary['TotalLiters'].sum()}")
print(f"[DEBUG] Top 5 пив:")
print(summary[['BeerName', 'TotalLiters', 'BeerSharePercent']].head(5).to_string())
```

---

## 📋 ЧЕК-ЛИСТ

- [ ] Проверить, что date_from/date_to правильно используются
- [ ] Добавить print/логирование для отладки дат
- [ ] Проверить, что OLAP запрос использует правильные даты
- [ ] Проверить при агрегировании (когда объединяются бары)
- [ ] Убедиться, что BeerSharePercent считается от ВСЕХ пив в периоде

---

## 🎯 СЛЕДУЮЩИЙ ШАГ

1. Добавить отладку согласно инструкции выше
2. Запустить анализ и посмотреть на консоль
3. Переслать лог с отладкой
4. Я помогу исправить точную проблему


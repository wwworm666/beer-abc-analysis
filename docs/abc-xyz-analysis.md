# ABC/XYZ Анализ

## Что это

Анализ ассортимента пива по двум методикам:
- **ABC:** Парето 80/15/5 — распределение по выручке и наценке
- **XYZ:** Коэффициент вариации (CV) — стабильность продаж

## Файлы

- [`core/abc_analysis.py`](../../core/abc_analysis.py) — ABC анализ, наценка
- [`core/xyz_analysis.py`](../../core/xyz_analysis.py) — XYZ анализ, CV вариация
- [`core/category_analysis.py`](../../core/category_analysis.py) — анализ по категориям
- [`core/draft_analysis.py`](../../core/draft_analysis.py) — анализ разливного
- [`routes/analysis.py`](../../routes/analysis.py) — Flask endpoint'ы

---

## Как работает

### ABC Анализ

#### Принцип Парето 80/15/5

Товары делятся на 3 группы:
- **A (80% выручки):** Основные товары, приносят 80% выручки
- **B (15% выручки):** Средние товары
- **C (5% выручки):** Мало продаваемые товары

#### Формула расчёта

```python
# core/abc_analysis.py
def calculate_abc(self, data, revenue_field='revenue'):
    """
    Сортируем товары по убыванию выручки,
    считаем накопленную долю, присваиваем категорию
    """
    # 1. Сортировка по убыванию выручки
    sorted_items = sorted(data, key=lambda x: x[revenue_field], reverse=True)

    # 2. Расчёт накопленной доли
    total = sum(item[revenue_field] for item in sorted_items)
    cumulative = 0

    for item in sorted_items:
        cumulative += item[revenue_field]
        cumulative_percent = (cumulative / total * 100) if total > 0 else 0

        # 3. Присвоение категории
        if cumulative_percent <= 80:
            item['abc_category'] = 'A'
        elif cumulative_percent <= 95:  # 80 + 15
            item['abc_category'] = 'B'
        else:
            item['abc_category'] = 'C'

    return sorted_items
```

#### Наценка по группам

Дополнительная классификация по наценке:
- **A (высокая):** Наценка ≥ 120%
- **B (средняя):** Наценка 100-120%
- **C (низкая):** Наценка < 100%

```python
def calculate_markup_category(self, markup_percent):
    if markup_percent >= 120:
        return 'A'
    elif markup_percent >= 100:
        return 'B'
    else:
        return 'C'
```

#### Матрица ABC × Наценка

| | Наценка A (≥120%) | Наценка B (100-120%) | Наценка C (<100%) |
|---|---|---|---|
| **A (80%)** | A×A — звёзды | A×B — рабочие лошадки | A×C — потери |
| **B (15%)** | B×A — потенциал | B×B — стабильные | B×C — сомнения |
| **C (5%)** | C×A — нишевые | C×B — заполнители | C×C — кандидаты на удаление |

---

### XYZ Анализ

#### Коэффициент вариации (CV)

Показывает стабильность продаж:
- **X (CV < 10%):** Стабильные продажи
- **Y (10% ≤ CV < 25%):** Колебания
- **Z (CV ≥ 25%):** Нестабильные продажи

#### Формула CV

```
CV = (σ / μ) × 100

где:
  σ = стандартное отклонение = √(Σ(xi - μ)² / n)
  μ = среднее значение = Σxi / n
  xi = продажи в период i
  n = количество периодов
```

#### Реализация

```python
# core/xyz_analysis.py
import numpy as np

def calculate_xyz(self, sales_data, period_field='date'):
    """
    sales_data: {date: revenue, ...}
    Returns: category ('X', 'Y', 'Z')
    """
    if len(sales_data) < 2:
        return 'X'  # Недостаточно данных

    values = list(sales_data.values())
    mean = np.mean(values)
    std = np.std(values, ddof=0)  # population std

    if mean == 0:
        return 'X'

    cv = (std / mean) * 100

    if cv < 10:
        return 'X'
    elif cv < 25:
        return 'Y'
    else:
        return 'Z'
```

---

### Анализ по категориям

#### Категории пива

```python
# core/category_analysis.py
CATEGORIES = {
    'light': 'Светлое',
    'dark': 'Тёмное',
    'wheat': 'Пшеничное',
    'ipa': 'IPA',
    'lager': 'Лагер',
    'stout': 'Стаут',
    'other': 'Другое'
}
```

#### Метрики по категориям

Для каждой категории рассчитывается:
- Выручка
- Доля в общей выручке (%)
- Количество проданных единиц
- Средняя наценка
- ABC категория

---

### Анализ разливного пива

#### Формула расчёта литров

```python
# core/draft_analysis.py
def calculate_liters(self, portions, portion_type):
    """
    portion_type: 'Kegs30L' | 'Kegs50L' | '0.5L' | '1L'
    """
    if portion_type == 'Kegs30L':
        return portions * 30
    elif portion_type == 'Kegs50L':
        return portions * 50
    elif portion_type == '0.5L':
        return portions * 0.5
    elif portion_type == '1L':
        return portions * 1.0
    else:
        return portions  # по умолчанию
```

#### Метрики разливного

- Литры проданные
- Порции (0.5L, 1L, Kegs30L, Kegs50L)
- Выручка
- Наценка

---

## API endpoint'ы

### ABC/XYZ анализ

```
POST /api/analyze
Body: {
    "dateFrom": "YYYY-MM-DD",
    "dateTo": "YYYY-MM-DD",
    "bar": "bolshoy" | "ligovskiy" | ... | ""
}
Response: {
    "abc": [...],   # ABC анализ по выручке
    "xyz": [...],   # XYZ анализ по стабильности
    "matrix": {...} # Матрица ABC×XYZ
}
```

### Категории

```
POST /api/categories
Body: {
    "dateFrom": "...",
    "dateTo": "..."
}
Response: {
    "categories": [
        {
            "name": "Светлое",
            "revenue": 123456,
            "share": 45.6,
            "items_count": 12,
            "avg_markup": 150.5
        }
    ]
}
```

### Разливное

```
POST /api/draft-analyze
Body: {
    "dateFrom": "...",
    "dateTo": "..."
}
Response: {
    "total_liters": 1234,
    "total_portions": 5678,
    "revenue": 987654,
    "by_beer": [...]
}
```

---

## Формулы

### Выручка товара
```
Выручка = Σ(DishDiscountSumInt) для товара
```

### Доля товара
```
Доля = (Выручка товара / Общая выручка) × 100%
```

### Накопленная доля
```
Накопленная = Σ(Доля всех предыдущих товаров) + Текущая доля
```

### Коэффициент вариации
```
CV = (σ / μ) × 100%

σ = √(Σ(xi - μ)² / n)
μ = Σxi / n
```

### Наценка
```
Наценка = (Выручка - Себестоимость) / Себестоимость × 100%
        = (DishDiscountSumInt - ProductCostBase.ProductCost) / ProductCostBase.ProductCost × 100%
```

---

## Зависимости

### От каких модулей зависит
- `core/olap_reports.py` → данные о продажах из iiko
- `core/data_processor.py` → подготовка DataFrame

### Кто использует
- Frontend анализа (`analysis.html`)
- Отчёты для управляющих
- Telegram bot (частично)

---

## Changelog

- **2026-03-27** — Создан документ abc-xyz-analysis.md с описанием формул ABC, XYZ, категорий и разливного

# Comparison Module — Percentage Display Fix

## Проблема

**Симптом:** Наценка розлив отображается как `19300.0%` вместо `193.0%`

```
Наценка розлив	19300.0%	24100.0%	4800.0%	-19.9%
```

## Причина

**Двойное умножение на 100:**

1. API возвращает значения уже в процентах: `193` (не `1.93`)
2. Formatter умножал на 100: `(193 * 100).toFixed(1)%` = `19300.0%`

**Откуда взялась путаница:**

В dashboard используется `formatPercent` из `utils.js`:
```javascript
export function formatPercent(value) {
    if (value == null) return '0%';
    return value.toFixed(1) + '%';  // НЕ умножает на 100
}
```

Но в comparison использовались кастомные форматтеры:
```javascript
// НЕПРАВИЛЬНО
formatter: (v) => `${(v * 100).toFixed(1)}%`
```

## Решение

### 1. Унифицировали форматтеры

**Было:**
```javascript
{ key: 'markupPercent', altKey: 'avg_markup', label: '% наценки',
  formatter: (v) => `${(v * 100).toFixed(1)}%` },
{ key: 'markupDraft', altKey: 'draft_markup', label: 'Наценка розлив',
  formatter: (v) => `${(v * 100).toFixed(1)}%` },
```

**Стало:**
```javascript
{ key: 'markupPercent', altKey: 'avg_markup', label: '% наценки',
  formatter: formatPercent },
{ key: 'markupDraft', altKey: 'draft_markup', label: 'Наценка розлив',
  formatter: formatPercent },
```

### 2. Исправили расчёт разницы

**Было:**
```javascript
// Умножали на 100, думая что значения в десятичных
formattedDiff = `${diff >= 0 ? '+' : ''}${(diff * 100).toFixed(1)} п.п.`;
```

**Стало:**
```javascript
// Значения уже в процентах, не умножаем
formattedDiff = `${diff >= 0 ? '+' : ''}${Math.abs(diff).toFixed(1)} п.п.`;
```

### 3. Исправили таблицу

В детальной таблице разница для процентных метрик теперь показывается в п.п.:

```javascript
let formattedDiff;
if (metric.key.includes('markup') || metric.key.includes('Share')) {
    formattedDiff = `${diff >= 0 ? '+' : ''}${Math.abs(diff).toFixed(1)} п.п.`;
} else {
    formattedDiff = `${diff >= 0 ? '+' : ''}${metric.formatter(Math.abs(diff))}`;
}
```

## Результат

### До:
```
Наценка розлив: 19300.0%
Разница: +4800.0 п.п.
```

### После:
```
Наценка розлив: 193.0%
Разница: +48.0 п.п.
```

## Урок

**Всегда проверяй формат данных от API:**
- Проценты могут приходить как `0.25` (десятичные) или `25` (уже проценты)
- Используй единый formatter из utils.js, не создавай кастомные
- Если видишь `* 100` в formatter — проверь, нужно ли это

**Правило:** Один formatter на один тип данных. Если dashboard использует `formatPercent`, comparison должен использовать тот же.

# API Endpoints для работы с планами

## Обзор

Дашборд использует следующие endpoints для работы с планами:

## 1. Получить план (GET)

**URL:** `/api/plans/{venueKey}/{periodKey}`

**Пример:**
```
GET /api/plans/kremenchugskaya/2025-11-17_2025-11-23
```

**Ответ (200 OK):**
```json
{
  "revenue": 100000,
  "checks": 500,
  "averageCheck": 200,
  "draftShare": 45.5,
  "packagedShare": 30,
  "kitchenShare": 24.5,
  "createdAt": "2025-11-17T23:07:21.115843",
  "updatedAt": "2025-11-17T23:07:38.998106"
}
```

**Ошибка (404):**
```json
{
  "error": "Plan not found"
}
```

---

## 2. Сохранить план (POST)

**URL:** `/api/plans/{venueKey}/{periodKey}`

**Body (JSON):**
```json
{
  "revenue": 100000,
  "checks": 500,
  "averageCheck": 200,
  "draftShare": 45.5,
  "packagedShare": 30,
  "kitchenShare": 24.5,
  "revenueDraft": 45500,
  "revenuePackaged": 30000,
  "revenueKitchen": 24500,
  "markupPercent": 215,
  "profit": 50000,
  "markupDraft": 230,
  "markupPackaged": 210,
  "markupKitchen": 195,
  "loyaltyWriteoffs": 1000
}
```

**Пример:**
```
POST /api/plans/kremenchugskaya/2025-11-17_2025-11-23
Content-Type: application/json

{...body...}
```

**Ответ (200 OK):**
```json
{
  "success": true,
  "message": "Plan saved successfully",
  "period": "2025-11-17_2025-11-23",
  "venue": "kremenchugskaya"
}
```

**Ошибка (400):**
```json
{
  "error": "Validation error: Missing required field: packagedShare"
}
```

---

## 3. Удалить план (DELETE)

**URL:** `/api/plans/{venueKey}/{periodKey}`

**Пример:**
```
DELETE /api/plans/kremenchugskaya/2025-11-17_2025-11-23
```

**Ответ (200 OK):**
```json
{
  "success": true,
  "message": "Plan deleted successfully"
}
```

**Ошибка (404):**
```json
{
  "error": "Plan not found"
}
```

---

## Требуемые поля

При сохранении плана требуются следующие поля:
- `revenue` - выручка (число)
- `checks` - количество чеков (число)
- `averageCheck` - средний чек (число)
- `draftShare` - доля розлива в % (число 0-100)
- `packagedShare` - доля фасовки в % (число 0-100)
- `kitchenShare` - доля кухни в % (число 0-100)
- `revenueDraft` - выручка от розлива (число)
- `revenuePackaged` - выручка от фасовки (число)
- `revenueKitchen` - выручка от кухни (число)
- `markupPercent` - процент наценки (число)
- `profit` - прибыль (число)
- `markupDraft` - наценка на розлив (число)
- `markupPackaged` - наценка на фасовку (число)
- `markupKitchen` - наценка на кухню (число)
- `loyaltyWriteoffs` - списания баллов (число)

---

## Примечания

1. **venueKey** - ключ заведения (например: `kremenchugskaya`, `bolshoy`, `ligovskiy`)
2. **periodKey** - ключ периода в формате `YYYY-MM-DD_YYYY-MM-DD` (например: `2025-11-17_2025-11-23`)
3. Доля розлива + доля фасовки + доля кухни должны быть = 100%
4. Все поля с данными должны быть числами
5. Даты автоматически добавляются при создании (`createdAt`, `updatedAt`)

---

## Совместимость

Для обратной совместимости также сохранены старые endpoints без venueKey:
- `GET /api/plans/<period_key>`
- `POST /api/plans`
- `DELETE /api/plans/<period_key>`

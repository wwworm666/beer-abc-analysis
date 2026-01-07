# Справочник iiko API - Все доступные значения

## Содержание
1. [Типы OLAP-отчетов](#типы-olap-отчетов)
2. [Типы данных полей](#типы-данных-полей)
3. [Поля группировки (groupByRowFields)](#поля-группировки)
4. [Поля агрегации (aggregateFields)](#поля-агрегации)
5. [Фильтры](#фильтры)
6. [Типы транзакций](#типы-транзакций)
7. [Типы документов](#типы-документов)
8. [Складские операции](#складские-операции)
9. [API поставщиков](#api-поставщиков)
10. [API событий](#api-событий)
11. [Используемые поля в проекте](#используемые-поля-в-проекте)

---

## Типы OLAP-отчетов

| Тип | Описание |
|-----|----------|
| `SALES` | Отчет по продажам (основной для ABC-анализа) |
| `TRANSACTIONS` | Отчет по проводкам (складские операции) |
| `DELIVERIES` | Отчет по доставке |
| `STOCK` | Контроль хранения остатков |

---

## Типы данных полей

| Тип | Описание |
|-----|----------|
| `ENUM` | Перечисление (предопределенные значения) |
| `STRING` | Строка |
| `ID` | Уникальный идентификатор (UUID) |
| `DATETIME` | Дата и время |
| `INTEGER` | Целое число |
| `PERCENT` | Процент |
| `DURATION_IN_SECONDS` | Длительность в секундах |
| `AMOUNT` | Количество |
| `MONEY` | Денежная сумма |

---

## Поля группировки

### Блюдо/Товар (Dish)
| Поле | Описание |
|------|----------|
| `Dish.Id` | ID блюда |
| `DishCode` | Код блюда |
| `DishName` | Название блюда |
| `DishFullName` | Полное название |
| `DishForeignName` | Иностранное название |
| `DishNum` | Номер |
| `Cooking.Place` | Место приготовления |
| `DishCategory` | Категория блюда |
| `DishMeasureUnit` | Единица измерения |

### Группа блюд (DishGroup)
| Поле | Описание |
|------|----------|
| `DishGroup` | Группа блюда |
| `DishGroup.Id` | ID группы |
| `DishGroup.Parent` | Родительская группа |
| `DishGroup.TopParent` | Группа верхнего уровня |
| `DishGroup.SecondParent` | Группа второго уровня |
| `DishGroup.ThirdParent` | Группа третьего уровня |

### Заказ (Order)
| Поле | Описание |
|------|----------|
| `OrderNum` | Номер заказа |
| `UniqOrderId` | Уникальный ID заказа |
| `UniqOrderId.Id` | UUID заказа |
| `GuestNum` | Количество гостей |
| `TableNum` | Номер стола |
| `NonCashPaymentType` | Тип безналичной оплаты |

### Дата/Время
| Поле | Описание |
|------|----------|
| `OpenDate.Typed` | Дата открытия (типизированная) |
| `CloseDate.Typed` | Дата закрытия |
| `PayDate.Typed` | Дата оплаты |
| `CookingFinishDate.Typed` | Дата окончания приготовления |
| `SessionDate.Typed` | Дата сессии |
| `PrechequeTime.Typed` | Время предчека |
| `OpenDate.Minutes` | Минута открытия |
| `CloseDate.Minutes` | Минута закрытия |
| `Hour` | Час |
| `DayOfWeek` | День недели |
| `Session.Number` | Номер сессии |

### Торговая точка (Store)
| Поле | Описание |
|------|----------|
| `Department` | Подразделение |
| `Department.Id` | ID подразделения |
| `Store.Name` | Название точки/склада |
| `DepartmentType` | Тип подразделения |
| `Section` | Секция зала |

### Персонал
| Поле | Описание |
|------|----------|
| `WaiterName` | Имя официанта |
| `WaiterId.Id` | ID официанта |
| `AuthorName` | Автор операции |
| `CashierName` | Имя кассира |
| `Manager.Name` | Имя менеджера |
| `Manager.Role` | Роль менеджера |
| `Delivery.Courier` | Курьер доставки |

### Гость/Клиент
| Поле | Описание |
|------|----------|
| `GuestNum` | Количество гостей |
| `OrderType` | Тип заказа |
| `Customer.Id` | ID клиента |
| `Customer.Name` | Имя клиента |
| `Customer.Phone` | Телефон клиента |

### Скидки/Надбавки
| Поле | Описание |
|------|----------|
| `DiscountType` | Тип скидки |
| `DiscountPercent` | Процент скидки |
| `RemovalType` | Тип удаления |
| `IncreaseType` | Тип надбавки |

### Оплата
| Поле | Описание |
|------|----------|
| `PayTypes` | Типы оплаты |
| `PayTypes.Combo` | Комбинация типов оплаты |
| `NonCashPaymentType` | Безналичный тип |

### Прочее
| Поле | Описание |
|------|----------|
| `Comment` | Комментарий |
| `CancelCause` | Причина отмены |
| `Conception` | Концепция |
| `CookingFinishDate.Typed` | Время готовности |
| `OrderDiscount.Type` | Тип скидки на заказ |

---

## Поля агрегации

### Основные метрики продаж
| Поле | Описание |
|------|----------|
| `DishDiscountSumInt` | Сумма со скидкой (целое) |
| `DishSumInt` | Сумма блюд (целое) |
| `DishAmountInt` | Количество блюд (целое) |
| `DiscountSum` | Сумма скидки |
| `IncreaseSum` | Сумма надбавки |
| `DishSum.withoutDiscount` | Сумма без скидки |
| `VAT.Sum` | Сумма НДС |

### Подсчет заказов
| Поле | Описание |
|------|----------|
| `UniqOrderId.OrdersCount` | Количество уникальных заказов |
| `ReceiptNum.OrdersCount` | Количество чеков |
| `GuestNum` | Количество гостей |
| `TableNum` | Количество столов |

### Себестоимость
| Поле | Описание |
|------|----------|
| `ProductCostBase.ProductCost` | Себестоимость продукта |
| `ProductCostBase.OneItem` | Себестоимость единицы |
| `ProductCostBase.MarkUp` | Наценка |
| `ProductCostBase.Percent` | Процент наценки |

### Средние значения
| Поле | Описание |
|------|----------|
| `Avg.Price` | Средняя цена |
| `Avg.Discount` | Средняя скидка |
| `Avg.GuestsCount` | Среднее количество гостей |

### Временные метрики
| Поле | Описание |
|------|----------|
| `WaiterDelay.Cooking` | Задержка официанта (готовка) |
| `WaiterDelay.Precheque` | Задержка до предчека |
| `CookingTime` | Время приготовления |
| `WaitingTimeAfterCooking` | Время ожидания после готовки |

### Балансы (для TRANSACTIONS)
| Поле | Описание |
|------|----------|
| `StartBalance.Amount` | Начальный остаток (количество) |
| `StartBalance.Money` | Начальный остаток (деньги) |
| `FinalBalance.Amount` | Конечный остаток (количество) |
| `FinalBalance.Money` | Конечный остаток (деньги) |
| `InSum` | Приход |
| `OutSum` | Расход |
| `CostCorrection` | Корректировка стоимости |

---

## Фильтры

### Типы фильтров
| Тип | Описание |
|-----|----------|
| `IncludeValues` | Включить только указанные значения |
| `ExcludeValues` | Исключить указанные значения |
| `DateRange` | Диапазон дат |
| `Range` | Числовой диапазон |
| `TopItems` | Топ N элементов |

### Часто используемые фильтры
| Поле | Описание |
|------|----------|
| `DeletedWithWriteoff` | Удалено со списанием |
| `OrderDeleted` | Заказ удален |
| `Storned` | Сторнировано |
| `OpenDate.Typed` | Дата открытия |
| `CloseDate.Typed` | Дата закрытия |
| `DishGroup.TopParent` | Группа верхнего уровня |
| `Store.Name` | Точка продаж |
| `Department` | Подразделение |
| `WaiterName` | Официант |
| `PayTypes` | Тип оплаты |
| `OrderType` | Тип заказа |

---

## Типы транзакций

### Приход
| Тип | Описание |
|-----|----------|
| `INVENTORY_INCOMMING` | Оприходование при инвентаризации |
| `INVOICE_INCOMING` | Приходная накладная |
| `INTERNAL_TRANSFER_INCOMMING` | Внутреннее перемещение (приход) |
| `PRODUCTION_INCOMMING` | Производство (приход) |
| `DISASSEMBLING_INCOMMING` | Разборка (приход) |
| `TRANSFORMATION_INCOMMING` | Трансформация (приход) |
| `EGAIS_INCOMING` | ЕГАИС приход |
| `EGAIS_RETURN_INCOMING` | ЕГАИС возврат (приход) |

### Расход
| Тип | Описание |
|-----|----------|
| `INVENTORY_WRITEOFF` | Списание при инвентаризации |
| `WRITEOFF` | Списание |
| `RETURN_INVOICE_OUTGOING` | Возвратная накладная (расход) |
| `INTERNAL_TRANSFER_OUTGOING` | Внутреннее перемещение (расход) |
| `PRODUCTION_OUTGOING` | Производство (расход) |
| `DISASSEMBLING_OUTGOING` | Разборка (расход) |
| `TRANSFORMATION_OUTGOING` | Трансформация (расход) |
| `SALES_OUTGOING` | Продажа (расход) |

### Продажи
| Тип | Описание |
|-----|----------|
| `SALE` | Продажа |
| `SALE_STORNO` | Сторно продажи |
| `PURCHASE` | Покупка |
| `PURCHASE_STORNO` | Сторно покупки |
| `DISCOUNT` | Скидка |
| `DISCOUNT_STORNO` | Сторно скидки |

### Денежные операции
| Тип | Описание |
|-----|----------|
| `CASH` | Наличные |
| `CASH_STORNO` | Сторно наличных |
| `CARD` | Карта |
| `CARD_STORNO` | Сторно карты |
| `CREDIT` | Кредит |
| `CREDIT_STORNO` | Сторно кредита |
| `CORRECTION` | Корректировка |
| `CORRECTION_STORNO` | Сторно корректировки |
| `EGAIS_SALE` | ЕГАИС продажа |
| `EGAIS_SALE_STORNO` | ЕГАИС сторно продажи |

### Прочие операции
| Тип | Описание |
|-----|----------|
| `RENEWAL_COST` | Обновление стоимости |
| `REVALUATION` | Переоценка |
| `COST_CORRECTION` | Корректировка стоимости |
| `OPENING_BALANCE` | Начальный баланс |
| `OUT_OF_STOCK` | Нет в наличии |
| `WASTE` | Отходы |
| `PREPARATION` | Приготовление |

---

## Типы документов

| Тип | Описание |
|-----|----------|
| `INCOMING_INVOICE` | Приходная накладная |
| `RETURN_INVOICE` | Возвратная накладная |
| `INTERNAL_TRANSFER` | Внутреннее перемещение |
| `PRODUCTION` | Акт приготовления |
| `SALES_DOCUMENT` | Документ продаж |
| `INVENTORY` | Инвентаризация |
| `WRITEOFF_DOCUMENT` | Акт списания |
| `DISASSEMBLING` | Акт разборки |
| `TRANSFORMATION` | Акт трансформации |
| `REVALUATION_DOCUMENT` | Акт переоценки |
| `OPENING_BALANCE_DOCUMENT` | Документ начального баланса |
| `CORRECTION_DOCUMENT` | Документ корректировки |
| `EGAIS_DOCUMENT` | Документ ЕГАИС |
| `SESSION_WRITE_OFF` | Списание за сессию |
| `WASTE_DOCUMENT` | Документ отходов |
| `PREPARATION_DOCUMENT` | Документ приготовления |
| `OUT_OF_STOCK_DOCUMENT` | Документ отсутствия |

---

## Складские операции

### Эндпоинты отчетов
| Эндпоинт | Описание |
|----------|----------|
| `/resto/api/v2/reports/olap` | OLAP отчеты v2 |
| `/resto/api/v2/reports/olap/presets` | Преднастроенные отчеты |
| `/resto/api/v2/reports/olap/byPresetId/{id}` | Отчет по пресету |
| `/resto/api/v2/reports/balance/stores` | Остатки по складам |
| `/resto/api/reports/store/numberOfWorkDays` | Количество рабочих дней |

### Параметры запроса
| Параметр | Описание |
|----------|----------|
| `key` | Токен авторизации |
| `dateFrom` | Дата начала (YYYY-MM-DD) |
| `dateTo` | Дата окончания (YYYY-MM-DD) |
| `summary` | Вычислять итоги (boolean) |

---

## API поставщиков

### Эндпоинты
| Эндпоинт | Описание |
|----------|----------|
| `/resto/api/suppliers` | Список поставщиков |
| `/resto/api/suppliers/{id}` | Информация о поставщике |
| `/resto/api/suppliers/{id}/priceLists` | Прайс-листы поставщика |

### Поля поставщика
| Поле | Описание |
|------|----------|
| `id` | UUID поставщика |
| `code` | Код поставщика |
| `name` | Название |
| `address` | Адрес |
| `phone` | Телефон |
| `email` | Email |
| `inn` | ИНН |
| `kpp` | КПП |
| `comment` | Комментарий |
| `cardNumber` | Номер карты |
| `accountingCategory` | Категория учета |
| `responsiblePerson` | Ответственное лицо |
| `responsiblePersonId` | ID ответственного |
| `deleted` | Удален |

### Поля прайс-листа
| Поле | Описание |
|------|----------|
| `dateStart` | Дата начала действия |
| `dateEnd` | Дата окончания |
| `product` | Продукт |
| `price` | Цена |
| `minOrderQuantity` | Мин. количество заказа |

---

## API событий

### Эндпоинты
| Эндпоинт | Описание |
|----------|----------|
| `/resto/api/events` | Получение событий |
| `/resto/api/events/session` | События сессии |
| `/resto/api/events/devices` | События устройств |

### Параметры
| Параметр | Описание |
|----------|----------|
| `from_revision` | С какой ревизии |
| `to_revision` | До какой ревизии |
| `types` | Типы событий |

### Типы событий
| Тип | Описание |
|-----|----------|
| `ORDER_CREATED` | Заказ создан |
| `ORDER_MODIFIED` | Заказ изменен |
| `ORDER_CLOSED` | Заказ закрыт |
| `ORDER_DELETED` | Заказ удален |
| `DISH_ADDED` | Блюдо добавлено |
| `DISH_MODIFIED` | Блюдо изменено |
| `DISH_DELETED` | Блюдо удалено |
| `PAYMENT_ADDED` | Оплата добавлена |
| `PAYMENT_DELETED` | Оплата удалена |
| `SESSION_OPENED` | Сессия открыта |
| `SESSION_CLOSED` | Сессия закрыта |
| `SHIFT_OPENED` | Смена открыта |
| `SHIFT_CLOSED` | Смена закрыта |
| `CASH_OPERATION` | Кассовая операция |
| `INVENTORY_OPERATION` | Складская операция |

### Поля события
| Поле | Описание |
|------|----------|
| `revision` | Номер ревизии |
| `timestamp` | Время события |
| `eventType` | Тип события |
| `deviceId` | ID устройства |
| `userId` | ID пользователя |
| `orderId` | ID заказа |
| `data` | Данные события (JSON) |

---

## Используемые поля в проекте

### Текущая конфигурация (core/olap_reports.py)

**Поля группировки:**
- `Store.Name` - Название точки
- `DishName` - Название блюда
- `DishGroup.TopParent` - Группа верхнего уровня
- `DishGroup.ThirdParent` - Группа третьего уровня
- `DishForeignName` - Иностранное название (для штрих-кодов)
- `OpenDate.Typed` - Дата
- `WaiterName` - Официант

**Поля агрегации:**
- `UniqOrderId` - Уникальный ID заказа
- `UniqOrderId.OrdersCount` - Количество заказов
- `DishAmountInt` - Количество блюд
- `DishDiscountSumInt` - Сумма со скидкой
- `DiscountSum` - Сумма скидки
- `ProductCostBase.ProductCost` - Себестоимость
- `ProductCostBase.OneItem` - Себестоимость единицы
- `ProductCostBase.MarkUp` - Наценка

**Фильтры:**
- `DeletedWithWriteoff` = false - Не удалённые
- `OrderDeleted` = false - Не удалённые заказы
- `DishGroup.TopParent` - Фильтр по категории
- `Store.Name` - Фильтр по точке

---

## Полезные комбинации для анализа

### ABC-анализ по выручке
```json
{
  "reportType": "SALES",
  "groupByRowFields": ["DishName", "DishGroup.TopParent"],
  "aggregateFields": ["DishDiscountSumInt", "DishAmountInt"],
  "filters": {
    "DeletedWithWriteoff": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]}
  }
}
```

### Анализ по точкам
```json
{
  "reportType": "SALES",
  "groupByRowFields": ["Store.Name", "DishName"],
  "aggregateFields": ["DishDiscountSumInt", "UniqOrderId.OrdersCount"]
}
```

### Динамика продаж по дням
```json
{
  "reportType": "SALES",
  "groupByRowFields": ["OpenDate.Typed", "DishName"],
  "aggregateFields": ["DishAmountInt", "DishDiscountSumInt"]
}
```

### Анализ себестоимости
```json
{
  "reportType": "SALES",
  "groupByRowFields": ["DishName"],
  "aggregateFields": ["ProductCostBase.ProductCost", "ProductCostBase.MarkUp", "DishDiscountSumInt"]
}
```

---

*Документ создан: 2025-12-23*
*Источник: Официальная документация iiko API*

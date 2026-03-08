# Анализ скидок

## Что это

Страница для анализа эффективности скидок и акций. Показывает: кто пользуется конкретной скидкой, сколько тратит, какие блюда берёт, и как часто заходит. Помогает ответить на вопрос: «Скидка привлекает допродажи или люди приходят только за халявой?»

## Файлы

| Файл | Назначение |
|------|-----------|
| `core/olap_reports.py` | Метод `get_discount_report()` — OLAP-запрос |
| `app.py` | Роуты `GET /discounts`, `POST /api/discount-analyze` |
| `templates/discounts.html` | Фронтенд — фильтры, карточки, таблица, модалка |

## Как работает

### Один OLAP — вся логика в Python

Ключевое решение: вместо трёх отдельных OLAP-запросов (список скидок, данные по гостям, частота визитов) — **один запрос**, который возвращает все строки с детализацией по блюдам. Агрегация делается на бэкенде.

```
groupByRowFields:
  Store.Name                    → Со склада (точка)
  Delivery.CustomerCardNumber   → Номер карты клиента
  Delivery.CustomerName         → ФИО клиента
  OrderNum                      → Номер чека
  DishName                      → Блюдо
  ItemSaleEventDiscountType     → Наименование скидки

aggregateFields:
  DishDiscountSumInt            → Сумма со скидкой, р.
  DiscountSum                   → Сумма скидки, р.
```

### Обработка в Python (app.py)

1. Из всех строк OLAP извлекаем уникальные `ItemSaleEventDiscountType` → заполняем dropdown
2. Группируем по `Delivery.CustomerCardNumber` (номер карты = уникальный гость):
   - **Визиты** = count unique `OrderNum`
   - **Суммы** = sum `DishDiscountSumInt` и `DiscountSum`
   - **Блюда** = список `DishName` с суммами (для модалки деталей)
3. Весь результат отправляется на фронт одним JSON — фильтрация по скидке происходит мгновенно на клиенте

### UX-флоу

```
[Период] + [Бар] → "Загрузить данные" → OLAP запрос
                                           ↓
                                    dropdown скидок заполняется
                                           ↓
                            [Выбрать скидку] → мгновенная фильтрация
                                           ↓
                              Карточки + таблица гостей
                                           ↓
                            [Клик по гостю] → модалка с деталями (блюда)
```

### Идентификация гостей

Гости идентифицируются по `Delivery.CustomerCardNumber` — номер карты клиента. В iiko лояльность часто привязана к телефону, и номер карты может быть самим телефоном (формат +7XXXXXXXXXX).

Также показываем `Delivery.CustomerName` (ФИО) для удобства.

### OLAP-поля для скидок (справка)

| Поле | Назначение | Тип |
|------|-----------|-----|
| `ItemSaleEventDiscountType` | Название скидки/надбавки | STRING, group+filter |
| `OrderDiscount.GuestCard` | Гостевая карта (привязана к скидке) | STRING, group+filter |
| `CardOwner` | Владелец гостевой карты | STRING, group+filter |
| `Delivery.CustomerCardNumber` | Номер карты клиента | STRING, group+filter |
| `Delivery.CustomerName` | ФИО клиента | STRING, group+filter |
| `DishDiscountSumInt` | Сумма со скидкой | MONEY, aggregate |
| `DiscountSum` | Сумма скидки | MONEY, aggregate |

## Changelog

- 2026-03-03: Создан модуль анализа скидок

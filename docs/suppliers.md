# suppliers.md — Справочник поставщиков (`/suppliers`, `/api/suppliers/*`)

> Этап 3 редизайна страницы «Заказы и остатки»
> ([docs/planning/stocks-order-redesign-2026-09-10.md](planning/stocks-order-redesign-2026-09-10.md)).
> Срок и дни поставки, кратность и написания поставщиков редактируются из интерфейса;
> в коде остались только стартовые значения и умолчания.

## Что это

До 2026-09-11 поставщик на странице заказа был сырой строкой `category` из
номенклатуры iiko (три написания одного «МаркетБир» давали три группы), а сроки поставки
жили в коде (`SUPPLIER_PARAMS`: 13 кухонных поставщиков, все пивные по умолчанию).
Справочник даёт экрану «К заказу» ([stocks.md](stocks.md)) и заказам
([orders.md](orders.md)):

| Поле | Что задаёт | На что влияет |
|---|---|---|
| Имя | каноническое имя поставщика | заголовок группы на «К заказу», текст заказа, карточка черновика |
| Написания (aliases) | как эта же компания называется в `category` iiko | склейка групп; поиск без регистра, кавычек и лишних пробелов |
| Срок поставки (`lead_time_days`) | дней доставки от отправки заказа до приёмки (0..60) | ближайшая и следующая поставка, горизонт формулы |
| Дни доставки (`delivery_weekdays`) | по каким дням поставщик привозит (пн = 0; по умолчанию пн–пт) | то же; заказ в пятницу при доставке пн–пт приедет в понедельник |
| Кратность (`pack_size`) | упаковка для фасовки и кухни (1..10000) | рекомендация округляется вверх; кеги считаются в литрах без кратности |
| Самовывоз (`self_pickup`) | Метро, Лента | пометка в заголовке группы (список покупок, а не сообщение поставщику) |
| Заметка | свободный текст до 500 символов | только для людей |

Поставщик, которого в справочнике нет, получает умолчания (`DEFAULT_LEAD_TIME_DAYS` = 3,
кратность 1, пн–пт) и помечен на «К заказу» «(по умолчанию)». Канал заказа (чат, сайт,
телефон) и контакт отложены на самый конец по решению владельца: пока все в чате.

## Файлы

- [core/supplier_directory.py](../core/supplier_directory.py) — модель, хранение, нормализация написаний, срез `DirectoryView` (`resolve`, `params`), `SEED_SUPPLIERS`.
- [routes/suppliers.py](../routes/suppliers.py) — blueprint `suppliers_bp`, API.
- [templates/suppliers.html](../templates/suppliers.html) — страница редактирования (роут `/suppliers` в `routes/pages.py`).
- [routes/stocks.py](../routes/stocks.py) — `_supplier_params(name, view)`, `_delivery_plan`; `SUPPLIER_PARAMS` оставлен как стартовые значения для совместимости.
- [routes/orders.py](../routes/orders.py) — ожидаемая дата поставки при «Отправлено» по сроку и дням доставки.
- [core/supplier_calendar.py](../core/supplier_calendar.py) — календарь: `next_delivery_date`, `delivery_after`, `horizon_days`.
- Тесты: [tests/test_supplier_directory.py](../tests/test_supplier_directory.py), раздел «этап 1» в [tests/test_stocks_routes.py](../tests/test_stocks_routes.py) (`test_order_board_uses_supplier_directory`).

Данные: `suppliers.json` на постоянном томе `/kultura` (локально `data/suppliers.json`, в git
не попадает). Пока файла нет, действует стартовый набор из кода; он записывается на диск
при первом сохранении из интерфейса. Lock-файл рядом: `suppliers.json.lock`.

## Как работает

### Модель и файл

```
suppliers[name] = {name, aliases: [str], lead_time_days: int, delivery_weekdays: [0..6],
                   pack_size: int, self_pickup: bool, note: str, updated_at, updated_by}
```

Чтение кэшируется по mtime файла; запись — `threading.Lock` + `portalocker` +
перечитывание внутри блокировки + атомарная запись (как у заказов). Битая запись в файле
пропускается с сообщением в лог, битый файл целиком — стартовый набор.

### Нормализация и разрешение имени

`normalize_name`: без регистра (`casefold`), без кавычек `" « » ' \``, пробелы схлопнуты.
`DirectoryView.resolve(category)`:

1. пустая строка → «Без поставщика» (`NO_SUPPLIER`);
2. нормализованное имя совпало с именем поставщика → это имя;
3. совпало с написанием → каноническое имя владельца написания;
4. иначе строка `category` как есть (поставщик «по умолчанию»).

Имена и написания уникальны между поставщиками: нельзя завести имя, равное чужому
написанию, или написание, уже принадлежащее другому; своё имя из написаний убирается.
Первое совпадение при построении индекса побеждает (сначала имена, потом написания).

### Как параметры попадают в формулу

На доске `order-board` срез справочника берётся один раз на запрос
(`get_supplier_directory().view()`), для каждой позиции `_supplier_params(category, view)`
даёт `name, lead_time_days, pack_size, delivery_weekdays, self_pickup, is_default`, а
`_delivery_plan(today, params)` — ближайшую и следующую поставку:

```
first_delivery   = next_delivery_date(today, lead_time_days, delivery_weekdays)
next_delivery    = delivery_after(first_delivery, delivery_weekdays)
days_to_delivery = first_delivery − today       (срочность)
horizon_days     = next_delivery − today        (формула «нужно»)
```

Пример. Среда, срок 2, доставка пн–пт: ближайшая пятница (2 дня), следующая понедельник
(5 дней) → нужно расход × (5 + 3). Тот же поставщик с доставкой только по понедельникам и
сроком 1: ближайшая понедельник (5 дней), следующая через неделю (12 дней).

### API

| Метод и путь | Тело | Ответ | Ошибки |
|---|---|---|---|
| `GET /api/suppliers` | — | `{suppliers[], unmapped_categories[{category, products}], nomenclature_available, defaults, stored}` | — |
| `PUT /api/suppliers/<name>` | `{aliases?, lead_time_days?, delivery_weekdays?, pack_size?, self_pickup?, note?, rename_to?}` — только переданные поля меняются | как GET + `supplier` | 400 с текстом проверки («Срок поставки: от 0 до 60», «Алиас … уже принадлежит …») |
| `DELETE /api/suppliers/<name>` | — | как GET | 404 |
| `POST /api/suppliers/<name>/aliases` | `{alias}` | как GET + `supplier` | 400, 404 |

`unmapped_categories` — категории товаров `GOODS`/`PREPARED` из текущей номенклатуры
(`get_stocks_nomenclature`), которые ни к кому не привязаны, по убыванию числа товаров;
без iiko список пуст и `nomenclature_available = false`. Имя в пути ищется без учёта
регистра и кавычек.

### Страница `/suppliers`

Карточка на поставщика: написания через запятую, срок, кратность, чекбоксы дней доставки,
самовывоз, заметка; «Сохранить», «Переименовать» (написания сохраняются), «Удалить».
Ошибка проверки показывается строкой в карточке. Поле «Имя нового поставщика» + «Добавить
поставщика». Блок «Категории iiko без поставщика»: для каждой — выпадающий список
«Привязать» как написание к существующему или «Завести как поставщика» с этим именем.
Ссылка «настроить» в заголовке каждой группы на «К заказу» ведёт сюда.

## Changelog

- **2026-09-11 (этап 3 редизайна)** — Модуль создан: `core/supplier_directory.py`,
  `routes/suppliers.py`, страница `/suppliers`; `routes/stocks.py` и `routes/orders.py`
  берут срок, дни доставки, кратность и каноническое имя из справочника;
  `SUPPLIER_PARAMS` стал стартовым набором.

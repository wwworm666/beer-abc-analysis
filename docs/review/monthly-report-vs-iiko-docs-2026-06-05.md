# Сверка: OLAP месячного отчёта vs документация iiko

Дата: 2026-06-05. Метод: многоагентный воркфлоу (5 направлений сверки -> состязательная
перепроверка каждого флага). Источник истины — документация iiko: локальный снапшот
`iiko-olap-docs/` (коммит 1985053), реестр `docs/technical/audits/OLAP_REQUEST_REGISTRY_2026-04-03.md`,
дамп колонок `data/olap_all_fields.json`, при нужде — живой `ru.iiko.help` через getMarkdown.
Код НЕ менялся — только фиксация.

## Итог

**Несоответствий документации iiko: 0.** Проверено 50 элементов (поля group-by/aggregate,
типы фильтров, enum-значения, семантика, тип отчёта, структура запроса, форма ответа) по всем
4 OLAP-методам месячного отчёта (`get_all_sales_report`, `get_draft_sales_report`,
`get_rfm_report`, `get_new_guests_count`). Все документированы и используются корректно. Поднято
3 флага первым проходом (статус «не удалось подтвердить») — все сняты на перепроверке.

## Что подтверждено документацией (ключевое)

| Элемент | Документация iiko | Вывод |
|---|---|---|
| `DateRange.to` — exclusive | `olap-otchety-v2.md:360` — `includeHigh` по умолчанию `false` -> верхняя граница НЕ включается | `_month_bounds` отдаёт 1-е число след. месяца как exclusive — корректно, июнь = `from 2026-06-01, to 2026-07-01` |
| `ProductCostBase.MarkUp` — дробь | `olap-otchety-v1.md:285` тип `PERCENT`; реестр:20 «fraction 0..1» | `avg_markup * 100` -> проценты, без двойного счёта |
| `DishDiscountSumInt` — оплачено | живой `olap-sales`: «Сумма без скидки − Сумма скидки», тип `MONEY` | верная база для выручки / среднего чека / трат гостя |
| `UniqOrderId.OrdersCount` | `olap-otchety-v1.md:302`, тип `AMOUNT`, счётчик заказов | верный счётчик чеков |
| `reportType: SALES` | `olap-otchety-v2.md:25,182-186` | валидный тип отчёта |
| Структура конверта | `olap-otchety-v2.md:147-176` — `{reportType, groupByRowFields, groupByColFields, aggregateFields, filters}` | совпадает; `buildSummary` опционально (по умолч. false) — месячный его не шлёт, читает только `data[]` |
| `DeletedWithWriteoff`/`OrderDeleted = IncludeValues[NOT_DELETED]` | `olap-otchety-v2.md:256-263` — ровно эта пара в эталонном примере | enum-значение валидно |

## 3 флага — подняты и сняты

### 1. `UniqOrderId.Id` как group-by — СНЯТ (валидно)
Первый проход не нашёл `UniqOrderId.Id` в текстовом каталоге (там только bare `UniqOrderId` и
`.OrdersCount`), а живая страница `olap-sales` отдаёт лишь русские отображаемые имена без
внутренних FieldName-кодов. Авторитетный источник — дамп `/v2/reports/olap/columns` в репозитории:
`data/olap_all_fields.json` (279 полей). Там `UniqOrderId.Id` -> `type=ID, groupingAllowed=true`.
Важная деталь: bare `UniqOrderId` имеет `type=INTEGER, groupingAllowed=FALSE`, поэтому группировать
по нему нельзя — **именно поэтому проект группирует по `.Id`** (UUID заказа), считая `DISTINCT` для
уникальных чеков. Использовано правильно.

### 2. `Delivery.Customer*` поля лояльности — СНЯТ (валидно)
Их нет в curated `IIKO_API_REFERENCE.md` (он неполный — там только `Customer.*`), но они есть в
снапшоте каталога доставки `iiko-olap-docs/olap-otchety-v1.md`:
- `Delivery.CustomerCardNumber` (`:50`, STRING, grouping=true) — ключ дедупликации в ТОП-гостях;
- `Delivery.CustomerName` (`:56`, STRING) — также в официальном SALES-примере `formirovanie-...md:58`;
- `Delivery.CustomerPhone` — в официальном SALES-примере `formirovanie-...md:59,124` (группировка + ответ);
- `Delivery.CustomerCreatedDateTyped` (`:54`, **тип DATE**, filtering=true) — валидно как DateRange-фильтр
  «новый гость»; это замена 4.2+ устаревшего STRING-поля `Delivery.CustomerCreatedDate`.

Официальный пример iiko смешивает `Delivery.Customer*` в group-by с `reportType: SALES` — значит
эти поля принимаются в SALES-отчёте. Соответствует коду.

### 3. `DishAmountInt` режет дробные литры — СНЯТ (предпосылка неверна)
Флаг исходил из того, что `DishAmountInt` используется КАК литры. Это не так. `_compute_liters`
([core/monthly_report.py:274-281](../../core/monthly_report.py#L274-L281)) делегирует в
`DraftAnalysis.get_style_summary`, где литры считаются как
`VolumeInLiters = DishAmountInt * PortionVolume` ([core/draft_analysis.py:194](../../core/draft_analysis.py#L194)),
а `PortionVolume` — объём порции в литрах, распарсенный из названия блюда (напр. «(0,5)» -> 0.5 л).
То есть `DishAmountInt` — это КОЛИЧЕСТВО порций (`olap-otchety-v1.md:218`, тип `AMOUNT`, не INTEGER —
поддерживает дробные), а литры = порции × объём порции. Корректно.

## Замечание для сведения (не баг)

`OrderNum` в `get_rfm_report` — реестр предупреждает, что он НЕ глобально уникален
(`OLAP_REQUEST_REGISTRY:19,41`). Но ТОП-гости месячного отчёта считают визиты по уникальной
`OpenDate.Typed` на карту, а НЕ по `OrderNum` — поэтому неуникальность `OrderNum` на счётчик визитов
не влияет. Риск смягчён по дизайну.

## Покрытие и оговорки

Агентов: 8 (5 сверок + 3 перепроверки). Сверка статическая (поля/фильтры/семантика по докам),
без обращения к живому iiko-серверу с реальными данными. Каталог FieldName-кодов брался из
`data/olap_all_fields.json` (дамп `/v2/reports/olap/columns`) — если серверная версия iiko
изменит метаданные, по правилу реестра (`:21`) живые `columns` важнее снапшота.

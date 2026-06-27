# Beer ABC/XYZ — Документация

> Карта по проекту. Source of truth — корневой [docs/](../docs/).
> Каждый модуль — отдельный .md.

---

## Структура проекта

```
Beer ABC/XYZ Analysis (Flask + iiko + ЧЗ)
├── Архитектура & инфраструктура → overview.md, PROJECT_STRUCTURE.md
├── Дашборд План/Факт            → dashboard.md
├── Employee Dashboard           → employee.md
├── ABC/XYZ Анализ               → abc-xyz-analysis.md
├── Анализ скидок (RFM)          → discounts.md
├── Анализ разливного            → draft-beer-errors.md, draft-beer-fixes.md
├── Конструктор отчётов          → explorer.md
├── Управление кранами           → taps.md
├── Редактор меню (/menu)        → menu-editor.md
├── Остатки + Сводный заказ      → stocks.md
├── Shelf-Life Cockpit           → expiration.md
├── iiko ↔ Честный Знак          → chz-stock-integration.md
├── Open-check Telegram bot      → open-check-bot.md
├── Планы выручки (4 точки)      → venues-plans.md
├── График смен                  → schedule.md
├── Авторизация (вход/аккаунты)  → auth.md
├── PWA Виджет Выручки           → pwa-widget.md
├── Frontend архитектура         → frontend.md
├── Design System                → design-system.md
└── Menu Card Tool (локальный)   → menu_tool/README.md
```

---

## Документы

| Файл | Описание | Статус |
|------|----------|--------|
| [context.md](context.md) | Быстрый контекст для Claude | ✅ |
| [docs/overview.md](../docs/overview.md) | Архитектура, blueprints, core-модули, внешние API, деплой Selectel | ✅ |
| [docs/PROJECT_STRUCTURE.md](../docs/PROJECT_STRUCTURE.md) | Дерево репозитория | ✅ |
| [docs/dashboard.md](../docs/dashboard.md) | Дашборд План/Факт — 15 метрик, AI-анализ | ✅ |
| [docs/monthly-report.md](../docs/monthly-report.md) | Вкладка «Месячный отчёт» — помесячная динамика, 16 графиков, YoY, кэш | ✅ |
| [docs/employee.md](../docs/employee.md) | Employee Dashboard — аналитика сотрудников, KPI, бонусы | ✅ |
| [docs/abc-xyz-analysis.md](../docs/abc-xyz-analysis.md) | ABC/XYZ анализ ассортимента пива | ✅ |
| [docs/discounts.md](../docs/discounts.md) | Анализ скидок — RFM-сегментация, ROI | ✅ |
| [docs/draft-beer-errors.md](../docs/draft-beer-errors.md) | Ошибки анализа разливного (классификация) | ✅ |
| [docs/draft-beer-fixes.md](../docs/draft-beer-fixes.md) | Исправления анализа разливного (2026-03-31) | ✅ |
| [docs/explorer.md](../docs/explorer.md) | Конструктор отчётов — `/explorer`, pivot iiko-данных | ✅ |
| [docs/taps.md](../docs/taps.md) | Управление 60 кранами (START/STOP/REPLACE) | ✅ |
| [docs/menu-editor.md](../docs/menu-editor.md) | Редактор меню `/menu`: единый каталог, цены из iiko, вкусы/теги, печать A4 (перенос из menu_tool) | ✅ |
| [docs/stocks.md](../docs/stocks.md) | Остатки: taplist/kitchen/bottles + Order Board (velocity) | ✅ |
| [docs/expiration.md](../docs/expiration.md) | Shelf-Life Cockpit — `/expiration` с tier-логикой и уценкой | ✅ |
| [docs/chz-stock-integration.md](../docs/chz-stock-integration.md) | iiko ↔ Честный Знак — dispenser API, КПП-привязка, авторефреш | ✅ |
| [docs/open-check-bot.md](../docs/open-check-bot.md) | Telegram-бот ежедневной проверки открытых смен 14:59 МСК | ✅ |
| [docs/venues-plans.md](../docs/venues-plans.md) | 4 точки, планы выручки, weekend weighting, override весов дней, «Планы по дням» | ✅ |
| [docs/schedule.md](../docs/schedule.md) | График смен: единая страница /schedule (просмотр + редактирование: кисть смен и выходных, планы/факт, пожелания, реестр, лента «кто что менял»); /schedule/edit → редирект. meeting notes | ✅ |
| [docs/auth.md](../docs/auth.md) | Авторизация: вход один раз (долгая сессия), глобальный гейт, личные аккаунты, /admin/users, стабильный SECRET_KEY | ✅ |
| [docs/ai-agent-concept.md](../docs/ai-agent-concept.md) | Концепт ИИ-агента NL-вопрос -> детерминированный ответ из iiko: gap-матрица 15 вопросов, лимиты API, архитектура | Концепт |
| [docs/frontend.md](../docs/frontend.md) | JS архитектура дашборда (15+ модулей) | ✅ |
| [docs/design-system.md](../docs/design-system.md) | Палитра, типографика, компоненты | ✅ |
| [docs/iiko-integration.md](../docs/iiko-integration.md) | iiko API: OLAP, cashshifts, auth (SHA-1) | ✅ |
| [docs/technical/OLAP_REPORTS_COLLECTION.md](../docs/technical/OLAP_REPORTS_COLLECTION.md) | Копии всех 24 OLAP-запросов проекта (дословные JSON-тела + потребители) | ✅ |
| [docs/technical/OLAP_REPORT_BUILDING_RULES.md](../docs/technical/OLAP_REPORT_BUILDING_RULES.md) | Правила создания OLAP-отчётов (iiko API): тело запроса, поля, фильтры, даты, чек-лист | ✅ |
| [docs/technical/audits/OLAP_AUDIT_2026-06-02.md](../docs/technical/audits/OLAP_AUDIT_2026-06-02.md) | Аудит OLAP-отчётов: 26 issue (4 high), приоритеты, рекомендации (без правок) | ✅ |
| [docs/lessons.md](../docs/lessons.md) | Баги, ловушки, паттерны (Problem→Cause→Solution) | ✅ |
| [docs/remote-sync.md](../docs/remote-sync.md) | Удалённая работа с бар-ПК через Tailscale + SSH | ✅ |
| [docs/CONNECTIVITY.md](../docs/CONNECTIVITY.md) | Подключение ко всем бар-ПК (SSH, сертификаты, доступ) | ✅ |
| [menu_tool/README.md](../menu_tool/README.md) | A4-карточки пивного меню — локальный Flask на :5050 | ✅ |
| [docs/CHANGELOG.md](../docs/CHANGELOG.md) | История изменений по сессиям | ✅ |

### Гайды и историческое (docs/)

| Папка | Что внутри |
|---|---|
| [docs/guides/](../docs/guides/) | DEPLOYMENT_GUIDE, BACKUP_SETUP, TAPS_*.md, TELEGRAM_BOT_GUIDE, ИНСТРУКЦИЯ_ДЛЯ_БАРМЕНОВ |
| [docs/technical/](../docs/technical/) | IIKO_API_REFERENCE, MAPPING_*, SYNC_FLOW_VISUAL, CODE_ANALYSIS_COMPLETE |
| [docs/changelog/](../docs/changelog/) | Исторические фиксы (BEER_SHARE_CALCULATION_BUG, FIX_DATE_HANDLING, etc.) |
| [docs/iiko-api/](../docs/iiko-api/) | Локальная копия всех статей API-документации портала `ru.iiko.help` (153 шт., оглавление в INDEX.md папки). Синк: `py -3 scripts/fetch_iiko_api_docs.py` |
| [docs/archive/](../docs/archive/) | Архивная документация |

---

## Quick Links

**Быстрый контекст для Claude** → [context.md](context.md)

**Нужно понять как работает проект?** → [docs/overview.md](../docs/overview.md)

**Словил баг?** → [docs/lessons.md](../docs/lessons.md)

**Работаешь с Employee?** → [docs/employee.md](../docs/employee.md)

**Работаешь с Dashboard?** → [docs/dashboard.md](../docs/dashboard.md)

**Работаешь с остатками/ЧЗ?** → [docs/stocks.md](../docs/stocks.md), [docs/chz-stock-integration.md](../docs/chz-stock-integration.md)

**Конструктор отчётов?** → [docs/explorer.md](../docs/explorer.md)

---

## Changelog (по версиям документации)

- **2026-06-26 (5):** График: «План / Факт по дням» переделан в ОДНУ таблицу по всем ТТ (колонки точек: факт над планом, + «Итого» день и %, строка «Итого» месяца), **без вкладок**. Секция **свёрнута по умолчанию** (заголовок-тоггл, в заголовке месячная сводка `Σфакт/Σплан·%`). Деньги в ячейках сокращены (`formatK`, точные — в title). Клик по дню — кто работал по каждой ТТ (`pfPeople`). Док: [schedule.md](../docs/schedule.md).
- **2026-06-26 (4):** График: «План / Факт по дням» — селектор точки (`Все` + по каждой точке: план/факт и смены именно этой точки, футер «Итого · точка»); мини-виджет «Выполнение плана» (`renderRecentCompletion`) в рейле под «Нагрузкой» на обеих страницах — позавчера/вчера/сегодня, % + факт/план, сегодня «идёт». Оба на уже загруженном `/plans`, без новых эндпоинтов. Док: [schedule.md](../docs/schedule.md).
- **2026-06-26 (2):** График: «Покрытие по дням недели» заменено на денежный виджет «План / Факт по дням» (`renderPlanFact` в `common.js`, на **обеих** страницах — владелец захотел выручку и в просмотре; доступ к `/schedule` и `/schedule/edit` одинаковый, равные права) — за каждый день план/факт выручки, % выполнения, кто на смене; клик по дню — разбивка по барам. Строится на фронте из `/plans` (факт = iiko OLAP) + смен, без нового эндпоинта и без второго вызова iiko. Чип сетки переработан (`buildChip`): имя целиком + капсула «День»/«с HH:MM» + факт вместо инициалов (ячейка не пустует). Фикс XSS `loc.name` в `renderDayPanel`. Удалены `compute_coverage_by_dow`/`renderCoverage`/CSS `.cov-*`/тест. Док: [schedule.md](../docs/schedule.md).
- **2026-06-26:** График: виджет «Покрытие по дням недели» (money-free) + «Нагрузка» и «Пожелания» продублированы на страницу просмотра `/schedule` (read-only). Общий эндпоинт `GET /api/schedule/widgets`. _Покрытие заменено в тот же день (см. запись выше)._ Док: [schedule.md](../docs/schedule.md).
- **2026-06-25:** График: убрана финансовая «Сводка месяца» (выручка → дашборд); «Нагрузка по сотрудникам» расширена — Смен/15 (норма `SHIFT_NORM`, цвет по выполнению), Подряд (макс. серия смен подряд, флаг переработки 5+), Часов, Без; группировка по `employee_id`. Из summary-роута убран лишний вызов iiko-часов. Док: [schedule.md](../docs/schedule.md) «Нагрузка по сотрудникам».
- **2026-06-24:** Привязка аккаунта к сотруднику графика (auth.db v3): `users.employee_iiko_id` — явная связь по стабильному id из iiko (раньше неявно по `display_name`). Выпадающий список сотрудников в `/admin/users`, `POST /api/auth/users/<id>/employee`. Пока только связь, без поведения. Опирается на график v6. Док: [auth.md](../docs/auth.md).
- **2026-06-24:** Сотрудники графика по стабильному id из iiko (shifts.db v6): `shifts.employee_id` + `schedule_employees.iiko_id` (GUID), имя — только показ/фоллбэк. `sync_employees(pairs, overrides)` бэкофиллит id у смен (override / точное имя / перестановка слов), канонизирует имена, распространяет переименования по id, дедупит legacy-строки. Переименование в iiko больше не плодит дублей. Тесты `tests/test_employee_ids.py`. Док: [schedule.md](../docs/schedule.md) «Идентичность сотрудника».
- **2026-06-24:** Визуальная причёска сетки графика: чип смены из насыщенной заливки роли в спокойную карточку с цветной полоской слева (`--role-color`), радиусы/тени `schedule.css` приведены к токенам `variables.css` (pill-кнопки, `--shadow-sm`), убрана колонка «Часов (iiko)» из «Нагрузки». Раскладка редактора: липкая панель управления + две колонки (сетка слева, рейл Нагрузка+Сводка справа на > 1180px). Только CSS + разметка + `buildChip`. Док: [schedule.md](../docs/schedule.md) «Внешний вид сетки» / «Раскладка редактора».
- **2026-06-24:** Оплата часов по ролям (shifts.db v5): график — единственный источник часов ЗП (iiko-часы для оплаты убраны), ставка у роли (`roles.rate_per_hour`), оплата = Σ по сменам (часы × ставка роли). Полная смена и вечер (с 18:00) — разные ставки. Док: [schedule.md](../docs/schedule.md) «Оплата часов по ролям», [employee.md](../docs/employee.md).
- **2026-06-24:** Журнал изменений графика «кто что менял» (на базе авторизации): таблица `schedule_audit` (схема `shifts.db` v4), запись автора (`current_user`) на правки смен / факта часов / выходных, панель «История изменений» на `/schedule/edit`. Док: [schedule.md](../docs/schedule.md).
- **2026-06-23:** Авторизация — полноценный вход (раньше всё было открыто): личные аккаунты (логин+пароль, хэш), глобальный `before_request`-гейт, «вход один раз» через стабильный `SECRET_KEY` + сессия 180 дней, `/admin/users` для владельца. Док: [auth.md](../docs/auth.md).
- **2026-06-19:** Редактор меню перенесён из `menu_tool/` в основное приложение (`/menu`): единый дедуплицированный каталог 108 карточек (библиотека + 21 кран), один вариант разлива 0,25/0,4/0,5, кнопка обновления цен из iiko, вкусы/теги/шкалы из веб-исследования, серверный рендер PDF. Док: [menu-editor.md](../docs/menu-editor.md).
- **2026-06-06:** Единый механизм дневного плана (`core/day_weights.py`) + override весов дней (праздник/закрытый день) + редактируемая под-вкладка «Планы по дням». Док: [venues-plans.md](../docs/venues-plans.md).
- **2026-06-04:** Новая вкладка дашборда «Месячный отчёт» — помесячная динамика метрик за год, 16 графиков, YoY-наложение, помесячный дисковый кэш. Док: [monthly-report.md](../docs/monthly-report.md).
- **2026-05-28:** Ревизия документации — `.claude/docs/*.md` перенесены в корневой `docs/`. SoT теперь в `docs/`. Обновлены `overview.md`, `PROJECT_STRUCTURE.md`, `stocks.md`, `lessons.md`, `INDEX.md`, `CLAUDE.md` под текущую реальность (11 blueprints, 33 core-модуля, menu_tool вынесен, Selectel-деплой).
- **2026-05-18:** Open-check Telegram bot — ежедневная проверка открытых смен в 4 барах KULT в 14:59 МСК. Позитив в группу, алармы в ЛС админам. Atomic file lock против double-fire под gunicorn 2-workers.
- **2026-05-17:** Конструктор отчётов — новая страница `/explorer` и API `/api/explorer/pivot`. Произвольная pivot-агрегация выручки из iiko.
- **2026-05-15:** Устранение костылей редактирования планов — удалены 5 legacy/костыльных endpoint'ов, добавлен cross-worker file lock через portalocker, новый `GET /api/plans/export` (xlsx). UI = единственный путь редактирования.
- **2026-04-30:** Shelf-Life Cockpit — новая страница `/expiration` с tier-классификацией.
- **2026-04-26:** Полная интеграция iiko ↔ Честный Знак (dispenser API, КПП-привязка, авторефреш 03:00).
- **2026-04-16:** Фикс дашборд-планов — убрана перезапись `/kultura/plansdashboard.json` из repo при рестарте.
- **2026-04-05:** Удалённый доступ к бар-ПК — Tailscale сеть + OpenSSH Server + paramiko.
- **2026-04-01:** Двухфайловая система планов — `plansdashboard.json` (месячные) + `daily_plans.json` (ежедневные, авто, Пт/Сб=2x).
- **2026-03-31:** RFM-сегментация гостей в анализе скидок.
- **2026-03-26:** PWA виджет выручки — 5 карточек с % выполнения.
- **2026-03-21:** Рефакторинг проекта — Flask Blueprints (app.py: 5199→31 строка).

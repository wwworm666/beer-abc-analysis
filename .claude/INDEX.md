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
├── Остатки + Сводный заказ      → stocks.md
├── Shelf-Life Cockpit           → expiration.md
├── iiko ↔ Честный Знак          → chz-stock-integration.md
├── Open-check Telegram bot      → open-check-bot.md
├── Планы выручки (4 точки)      → venues-plans.md
├── График смен                  → schedule.md
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
| [docs/employee.md](../docs/employee.md) | Employee Dashboard — аналитика сотрудников, KPI, бонусы | ✅ |
| [docs/abc-xyz-analysis.md](../docs/abc-xyz-analysis.md) | ABC/XYZ анализ ассортимента пива | ✅ |
| [docs/discounts.md](../docs/discounts.md) | Анализ скидок — RFM-сегментация, ROI | ✅ |
| [docs/draft-beer-errors.md](../docs/draft-beer-errors.md) | Ошибки анализа разливного (классификация) | ✅ |
| [docs/draft-beer-fixes.md](../docs/draft-beer-fixes.md) | Исправления анализа разливного (2026-03-31) | ✅ |
| [docs/explorer.md](../docs/explorer.md) | Конструктор отчётов — `/explorer`, pivot iiko-данных | ✅ |
| [docs/taps.md](../docs/taps.md) | Управление 60 кранами (START/STOP/REPLACE) | ✅ |
| [docs/stocks.md](../docs/stocks.md) | Остатки: taplist/kitchen/bottles + Order Board (velocity) | ✅ |
| [docs/expiration.md](../docs/expiration.md) | Shelf-Life Cockpit — `/expiration` с tier-логикой и уценкой | ✅ |
| [docs/chz-stock-integration.md](../docs/chz-stock-integration.md) | iiko ↔ Честный Знак — dispenser API, КПП-привязка, авторефреш | ✅ |
| [docs/open-check-bot.md](../docs/open-check-bot.md) | Telegram-бот ежедневной проверки открытых смен 14:59 МСК | ✅ |
| [docs/venues-plans.md](../docs/venues-plans.md) | 4 точки, планы выручки, weekend weighting | ✅ |
| [docs/schedule.md](../docs/schedule.md) | График смен, роли, meeting notes | ✅ |
| [docs/frontend.md](../docs/frontend.md) | JS архитектура дашборда (15+ модулей) | ✅ |
| [docs/design-system.md](../docs/design-system.md) | Палитра, типографика, компоненты | ✅ |
| [docs/iiko-integration.md](../docs/iiko-integration.md) | iiko API: OLAP, cashshifts, auth (SHA-1) | ✅ |
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
| iiko API спецификации | Локальная копия удалена 2026-05-29. Источник: портал `ru.iiko.help` — markdown через `/helper/articles/{раздел}/{slug}/?action=getMarkdown` (см. CLAUDE.md) |
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

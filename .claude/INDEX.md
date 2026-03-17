# Beer ABC/XYZ — Документация

> Карта по проекту. Каждый модуль — отдельный файл.

---

## Структура проекта

```
Beer ABC/XYZ Analysis
├── Дашборд План/Факт     → dashboard.md
├── Employee Dashboard    → employee.md
├── ABC/XYZ Анализ        → analytics.md
├── Анализ скидок          → discounts.md
├── Управление кранами    → taps.md
├── Design System         → design-system.md
└── Общее                 → overview.md
```

---

## Документы

| Файл | Описание | Статус |
|------|----------|--------|
| [context.md](context.md) | Быстрый контекст для Claude | ✅ актуально |
| [overview.md](docs/overview.md) | Архитектура, технологии, структура кода | ✅ актуально |
| [employee.md](docs/employee.md) | Employee Dashboard — аналитика сотрудников | ✅ актуально |
| [analytics.md](docs/analytics.md) | ABC/XYZ анализ — классификация пива | 📝 TODO |
| [dashboard.md](docs/dashboard.md) | Дашборд План/Факт — 15 метрик, AI-анализ | ✅ актуально |
| [optimization-dashboard.md](docs/optimization-dashboard.md) | План оптимизации производительности /dashboard | ✅ актуально |
| [discounts.md](docs/discounts.md) | Анализ скидок — ROI, сегментация гостей, drill-down по барам | ✅ актуально |
| [taps.md](docs/taps.md) | Управление 60 кранами | 📝 TODO |
| [design-system.md](docs/design-system.md) | Дизайн-система: CSS стек, навигация, скелет новой страницы | ✅ актуально |
| [lessons.md](docs/lessons.md) | Баги, ловушки, паттерны | ✅ актуально |

---

## Quick Links

**Быстрый контекст для Claude** → [context.md](context.md)

**Нужно понять как работает проект?** → [overview.md](docs/overview.md)

**Словил баг?** → [lessons.md](docs/lessons.md)

**Работаешь с Employee?** → [employee.md](docs/employee.md)

**Работаешь с Dashboard?** → [dashboard.md](docs/dashboard.md)

---

## Changelog

- 2026-03-17: Добавлена страница /wiki — встроенная вики с TOC sidebar (12 разделов). Удалён gitbook/
- 2026-03-03: Добавлен discounts.md — модуль анализа скидок
- 2026-02-07: Добавлен optimization-dashboard.md — план оптимизации производительности
- 2026-01-28: Обновлены employee.md (12 метрик, карты лояльности), overview.md, context.md, lessons.md
- 2026-01-26: Обновлены overview.md, dashboard.md. Добавлен context.md
- 2026-01-25: Создана модульная структура документации

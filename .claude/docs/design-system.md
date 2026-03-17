# Design System — Warm Minimalism 2026

## Что это

Единая дизайн-система для всех страниц проекта. Определяет: какие CSS подключать, как вставлять навигацию, какие переменные использовать, и как собрать новую страницу за 5 минут. Появилась в марте 2026 после унификации 12 страниц к стилю дашборда.

## Файлы

### CSS стек (подключать в этом порядке)

```
static/dashboard/styles/
├── fonts.css       ← @font-face IBM Plex Mono (400, 500, 600, 700)
├── variables.css   ← :root переменные + [data-theme="dark"]
├── base.css        ← Reset, body, .container, .btn, input/select, .api-status, .theme-toggle
├── sidebar.css     ← Sidebar panel, backdrop, .header-bar, responsive
└── mobile.css      ← Mobile breakpoints

static/
├── logo.css        ← Typewriter logo animation (> kultura.os_)
└── logo.js         ← Typewriter effect для .header-bar-logo .logo-text
```

### Навигация

```
templates/shared/nav.html   ← Sidebar + Header Bar + Theme JS + Active Link Detection
```

## Как собрать новую страницу

### Минимальный скелет

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Название — Beer Analytics</title>

    <!-- Shared CSS (ПОРЯДОК ВАЖЕН) -->
    <link rel="stylesheet" href="/static/dashboard/styles/fonts.css">
    <link rel="stylesheet" href="/static/dashboard/styles/variables.css">
    <link rel="stylesheet" href="/static/dashboard/styles/base.css">
    <link rel="stylesheet" href="/static/dashboard/styles/sidebar.css">
    <link rel="stylesheet" href="/static/dashboard/styles/mobile.css">
    <link rel="stylesheet" href="/static/logo.css">

    <!-- Page-specific CSS (только уникальные стили страницы) -->
    <style>
        .my-card { ... }
    </style>
</head>
<body>
    <div class="container">
        {% set page_title = "Название" %}
        {% set page_subtitle = "Краткое описание" %}
        {% include 'shared/nav.html' %}

        <!-- Контент страницы -->
        <div class="card">
            ...
        </div>
    </div>

    <script>
        // API check (обязательно)
        window.dashboardCheckApi = async function() {
            const statusElement = document.getElementById('api-status');
            const textElement = statusElement.querySelector('.api-status-text');
            statusElement.className = 'api-status checking';
            textElement.textContent = 'Проверка подключения...';
            try {
                const response = await fetch('/api/connection-status');
                const data = await response.json();
                if (response.ok && data.status === 'connected') {
                    statusElement.className = 'api-status connected';
                    textElement.textContent = 'iiko API подключен';
                } else {
                    statusElement.className = 'api-status error';
                    textElement.textContent = 'Ошибка подключения';
                }
            } catch (error) {
                statusElement.className = 'api-status error';
                textElement.textContent = 'Ошибка подключения';
            }
        };

        document.addEventListener('DOMContentLoaded', function() {
            window.dashboardCheckApi();
            setInterval(window.dashboardCheckApi, 60000);
        });

        // ... остальная логика страницы
    </script>
    <script src="/static/logo.js"></script>
</body>
</html>
```

### Что даёт nav.html автоматически

При `{% include 'shared/nav.html' %}` ты получаешь:

1. **Sidebar** — боковая панель с навигацией (все 11 ссылок)
2. **Header Bar** — `[кнопка меню] [page_title / page_subtitle] [> kultura.os_]`
3. **Theme toggle** — переключатель светлая/темная в sidebar footer
4. **API status** — индикатор подключения к iiko в sidebar footer
5. **Active link detection** — текущая страница подсвечивается автоматически по `window.location.pathname`
6. **Keyboard shortcuts** — `M` открывает/закрывает sidebar, `Esc` закрывает
7. **`window.dashboardSetTheme(theme)`** — глобальная функция переключения темы
8. **Saved theme** — тема сохраняется в localStorage и применяется при загрузке

### Переменные для nav.html

```jinja2
{% set page_title = "Название" %}        {# обязательно #}
{% set page_subtitle = "Подзаголовок" %}  {# опционально #}
{% include 'shared/nav.html' %}
```

## Цветовая палитра

### Light Theme

| Переменная | Значение | Назначение |
|-----------|---------|-----------|
| `--bg-primary` | `#FAF9F7` | Фон страницы (теплый кремовый) |
| `--bg-secondary` | `#FFFFFF` | Фон карточек |
| `--bg-tertiary` | `#F4F3F0` | Hover, вложенные блоки |
| `--text-primary` | `#1a1a1a` | Основной текст |
| `--text-secondary` | `#666666` | Вторичный текст |
| `--text-tertiary` | `#999999` | Подписи, hints |
| `--accent` | `#D97757` | Терракотовый акцент |
| `--accent-hover` | `#C2664A` | Hover акцента |
| `--accent-light` | `#F5E8E3` | Светлый фон для акцента |
| `--border-color` | `#E8E6E3` | Границы |
| `--success` | `#059669` | Зеленый (OK, рост) |
| `--warning` | `#D97706` | Желтый (внимание) |
| `--danger` | `#DC2626` | Красный (ошибка, падение) |

### Dark Theme

Активируется через `[data-theme="dark"]`. Фоны — теплые темно-коричневые (НЕ чистый черный):
- `--bg-primary: #1C1917`
- `--bg-secondary: #292524`
- `--accent: #E89779` (светлее для контраста)

## Типографика

- **Шрифт:** IBM Plex Mono (400, 500, 600, 700)
- **Размер:** 15px base, line-height 1.6
- **Подход:** Моноширинный шрифт = финтех-эстетика, "командная строка"

## Ключевые компоненты

### Карточка `.card`

```css
.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;        /* или var(--border-radius) = 24px для dashboard */
    padding: 32px;
    margin-bottom: 24px;
}
```

### Кнопка `.btn`

```css
/* base.css уже определяет .btn с pill-shape */
.btn {
    background: var(--accent);
    color: white;
    border-radius: var(--border-radius-pill);  /* 999px */
    padding: 14px 28px;
}
```

Если нужна менее "pill" кнопка, переопредели `border-radius: 6px` в page-specific стилях.

### Таблица

```css
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
thead { border-bottom: 2px solid var(--border-color); }
th { text-align: left; padding: 12px 16px; color: var(--text-secondary);
     text-transform: uppercase; font-size: 0.8rem; }
td { padding: 16px; border-bottom: 1px solid var(--border-color); }
```

### Flatpickr (выбор дат)

Подключай CDN в `<head>`:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/l10n/ru.js"></script>
```

Dark theme стили для flatpickr (добавь в page-specific `<style>`):
```css
.flatpickr-calendar { border-radius: 6px; border: 1px solid var(--border-color); }
[data-theme="dark"] .flatpickr-calendar { background: var(--bg-secondary); }
[data-theme="dark"] .flatpickr-day { color: var(--text-primary); }
.flatpickr-day.selected, .flatpickr-day.startRange, .flatpickr-day.endRange {
    background: var(--accent) !important; border-color: var(--accent) !important;
}
```

## Ловушки и антипаттерны

### Jinja2 внутри HTML-комментариев

**НИКОГДА** не пиши `{% %}` внутри `<!-- -->`. Jinja2 обрабатывает шаблонные теги ДАЖЕ внутри HTML-комментариев. Используй Jinja2 комментарии: `{# ... #}`.

Мы словили бесконечную рекурсию (`RecursionError: maximum recursion depth exceeded`) из-за:
```html
<!-- Usage: {% include 'shared/nav.html' %} -->   <-- СЛОМАЕТ ВСЕ
{# Usage: include 'shared/nav.html' #}            <-- правильно
```

### `checkApiConnection` -> `window.dashboardCheckApi`

Все страницы должны определять и вызывать `window.dashboardCheckApi()`. Старое имя `checkApiConnection()` не существует. Если JS упадет на вызове несуществующей функции, весь остальной код в DOMContentLoaded (включая flatpickr init) не выполнится.

### Порядок скриптов

1. Сначала `{% include 'shared/nav.html' %}` (определяет `window.dashboardSetTheme`)
2. Потом page-specific `<script>` (определяет `window.dashboardCheckApi`)
3. В конце `<script src="/static/logo.js"></script>` (typewriter эффект)

### Container обязателен

Весь контент должен быть внутри `<div class="container">`. Без него header-bar не получит `max-width: 1400px` и padding.

## Текущие страницы

| Route | Template | page_title | page_subtitle |
|-------|----------|-----------|---------------|
| `/` | `dashboard/base.html` | Дашборд | Выручка, средний чек, эффективность смен |
| `/packaging` | `index.html` | ABC/XYZ анализ | Классификация ассортимента по выручке и стабильности |
| `/draft` | `draft.html` | Анализ проливов | Контроль потерь разливного пива |
| `/discounts` | `discounts.html` | Анализ акций | ROI скидок, сегментация гостей, эффективность промо |
| `/waiters` | `waiters.html` | Анализ проливов по барменам | Сравнение продаж |
| `/employee` | `employee.html` | Дашборд сотрудника | Персональная аналитика по всем метрикам |
| `/bonus` | `bonus.html` | Расчёт премий | Мотивация по плану выручки и KPI |
| `/schedule` | `schedule.html` | График | Расписание, нагрузка, подмены |
| `/taps` | `taps.html` | Мониторинг кранов | Ротация сортов, остатки кег, простои |
| `/stocks` | `stocks.html` | Заказы и остатки | Стоки, заказы, оборачиваемость |
| `/taps/main` | `taps_main.html` | Мониторинг кранов | Активность и простои по барам |
| `/taps/<bar>` | `taps_bar.html` | Краны -- {{ bar_name }} | Ротация и управление кранами бара |
| `/wiki` | `wiki.html` | Вики | Документация и справочные материалы |

## Changelog

- 2026-03-17: Добавлена страница /wiki в таблицу маршрутов + ссылка «Вики» в sidebar
- 2026-03-17: Создан design-system.md -- полный гайд по дизайн-системе
- 2026-03-17: Унификация всех 12 страниц к warm minimalism, создание shared/nav.html

# Дизайн-система Beer ABC Analysis

## Что это

Единая дизайн-система для всех страниц приложения. Основана на принципах **тёплого минимализма** с финтех-эстетикой 2026 года.

## Философия

- **Тёплые тона** — кремовые фоны, терракотовый акцент
- **Моноширинный шрифт** — IBM Plex Mono для всей типографики
- **Минимализм** — только необходимые элементы, никаких декоративных украшений
- **Плавные переходы** — 150-200ms cubic-bezier для всех анимаций
- **Щедрые отступы** — воздух между элементами

---

## Запрещено (Anti-patterns)

**Никогда не использовать:**

| Запрет | Почему | Чем заменить |
|--------|--------|--------------|
| 🚫 Смайлики/эмодзи в UI | Непрофессионально, не соответствует финтех-стилю | Текстовые иконки, SVG |
| 🚫 Пёстрые цветные надписи | Визуальный шум, трудно читать | Только статусные цвета (success/warning/danger) |
| 🚫 Градиенты на тексте | Выглядит дешево, плохая читаемость | Сплошные цвета из палитры |
| 🚫 Более 3 цветов в компоненте | Нарушает минимализм | 1 основной + 1 акцент + 1 статусный |
| 🚫 Случайные HEX-цвета | Ломает консистентность | Только CSS переменные (`var(--name)`) |
| 🚫 Декоративные иконки без функции | Визуальный мусор | Только функциональные элементы |

**Правило:** Если элемент не несёт функциональной нагрузки — удалить.

---

## Файлы

```
static/dashboard/styles/
├── variables.css      ← CSS переменные (цвета, отступы, радиусы)
├── fonts.css          ← Подключение IBM Plex Mono
├── base.css           ← Базовые стили, кнопки, инпуты + мобильный каркас (≤768px)
├── cards.css          ← Карточки метрик и компонентов
├── charts.css         ← Графики и визуализации
├── tabs.css           ← Табы и навигация
├── sidebar.css        ← Боковая панель
├── mobile.css         ← Адаптив контента (карточки, таблицы, графики)
└── animations.css     ← Анимации
```

---

## Цветовая палитра

### Light Theme

| Переменная | Значение | Назначение |
|------------|----------|------------|
| `--bg-primary` | `#FAF9F7` | Основной фон страницы |
| `--bg-secondary` | `#FFFFFF` | Фон карточек |
| `--bg-tertiary` | `#F4F3F0` | Фон hover-состояний |
| `--text-primary` | `#1a1a1a` | Основной текст |
| `--text-secondary` | `#666666` | Вторичный текст, лейблы |
| `--text-tertiary` | `#999999` | Подписи, placeholder |
| `--accent` | `#D97757` | **Терракотовый акцент** |
| `--accent-hover` | `#C2664A` | Акцент при наведении |
| `--border-color` | `#E8E6E3` | Границы элементов |

### Dark Theme

| Переменная | Значение | Назначение |
|------------|----------|------------|
| `--bg-primary` | `#1C1917` | Тёмный тёплый фон |
| `--bg-secondary` | `#292524` | Фон карточек |
| `--text-primary` | `#FAF9F7` | Светлый текст |
| `--accent` | `#E89779` | Светлый терракотовый |

### Статусы

```css
--success: #059669;     /* Зелёный */
--warning: #D97706;     /* Янтарный */
--danger: #DC2626;      /* Красный */
```

---

## Типографика

### Шрифт

```css
font-family: 'IBM Plex Mono', 'Courier New', monospace;
```

### Иерархия

| Элемент | Размер | Вес | Трекинг |
|---------|--------|-----|---------|
| H1 | `3rem` | 700 | `0.02em` |
| H2 | `1.75rem` | 700 | `-0.01em` |
| H3 | `1.1rem` | 600 | `-0.01em` |
| Label | `0.85rem` | 600 | `0.05em` (uppercase) |
| Body | `15px` | 400 | normal |
| Small | `0.75rem` | 500-600 | `0.05em` (uppercase) |

### Числа

```css
font-variant-numeric: tabular-nums;  /* Табличные цифры для выравнивания */
letter-spacing: -0.02em;  /* Плотный трекинг для крупных чисел */
```

---

## Шкала радиусов — один радиус на уровень

| Уровень | Радиус | Что |
|---------|--------|-----|
| Панели и карточки | `14px` | шапка страницы, шапка фильтров, строка вкладок, карточка метрики, выпадающий список |
| Кнопки внутри панелей | `10px` | стрелки, подпись периода, кнопки экспорта, пункты списка, кнопка меню |
| Таблетки и шкалы | `999px` | вкладки, треки шкал, свотчи легенды, чипы |

Смешивать радиусы на одном уровне нельзя: 8px рядом с 10px читается как
случайность, а не как решение. Крупные `--border-radius` (24px) остаются для
страниц вне дашборда.

**Легенда — один раз на страницу.** Если один и тот же условный знак нужен многим
блокам, он ставится в общей строке (у дашборда — в строке вкладок), а не
повторяется в каждом заголовке группы.

---

## Компоненты

### Карточка (Card)

```css
.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 24px;           /* --border-radius */
    padding: 32px;
    transition: all 0.2s ease;
}

.card:hover {
    box-shadow: 0 4px 12px var(--shadow);
    transform: translateY(-2px);
}
```

**Требования:**
- Всегда белый/тёмный фон
- Тонкая граница 1px
- Большие радиусы 24px
- Hover-эффект с подъёмом

### Кнопка (Button)

```css
.btn {
    background: var(--accent);
    color: white;
    border: none;
    padding: 14px 28px;
    border-radius: 999px;          /* Pill-shape */
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
}

.btn:hover {
    background: var(--accent-hover);
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
}
```

**Варианты:**
- `.btn` — первичная (терракотовая)
- `.btn-secondary` — вторичная (серый фон)

### Инпуты (Form Controls)

```css
input, select {
    padding: 12px 16px;
    border: 1px solid var(--border-color);
    border-radius: 24px;           /* --border-radius */
    font-size: 0.95rem;
    font-family: var(--font-family);
    background: var(--bg-secondary);
    transition: all 0.15s ease;
}

input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-light);
}
```

**Label:**
```css
label {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
}
```

### Метрика (Metric Card)

```css
.metric-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    padding: 20px;
    transition: all 0.15s ease;
}

.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(26, 26, 26, 0.08);
}
```

**Структура (редизайн 2026-08-11):**
```
┌──────────────────────────────────┐
│ ВЫРУЧКА                       ▾  │  ← metric-name + каретка раскрытия
│ 1 478 025 ₽                      │  ← metric-value (28px, 700)
│                                  │
│ [████████████████░░]      102%   │  ← mc-bar-row (акцент, цветной процент)
│ [█████████████████░]      109%   │  ← mc-bar-row-prev (--bar-prev, серый)
│                                  │
│ +25 525 ₽        план 1 452 500 ₽│  ← mc-footer: отклонение + план
└──────────────────────────────────┘
```

**Две шкалы одной длины** — сравнение с предыдущим периодом читается без чисел.
Подписей у шкал нет: их роль выполняет **легенда в разделителе группы**, иначе
колонка подписей отъедала треть карточки и шкала становилась слишком короткой,
чтобы сравнивать.

**Цвет сигналит один раз.** Статус несёт только процент выполнения
(`.mc-pct.success/.warning/.danger`). Точки-индикатора на десктопе нет, отклонение
нейтральное — знак `+`/`−` уже показывает направление. На экране из 16 карточек
второй и третий носитель того же сигнала превращают его в рябь.

Точка статуса (`.m-dot`) осталась только на мобильных карточках, где процент
показан мелко.

Шкала прошлого периода дорисовывается после догрузки его данных, с плавным
появлением (`mcPrevIn`).

### Разделитель группы

Группы метрик разделяются подписью с линией, а не плашкой-заголовком.
Справа — легенда шкал, одна на группу:

```
ВЫРУЧКА ───────────────────────────────  ▬ сейчас   ▬ было
```

```css
.mg-separator { display: flex; align-items: center; gap: 14px; }
.mg-title { font-size: 11px; font-weight: 600; letter-spacing: .12em;
            color: var(--text-secondary); }
.mg-line  { flex: 1; height: 1px; background: var(--border-color); }
.mg-swatch { width: 14px; height: 5px; border-radius: 999px; background: var(--accent); }
.mg-swatch-prev { background: var(--bar-prev); }
```

Легенда скрыта, пока вторая шкала не загрузилась: подпись «было» без единой
серой шкалы вводит в заблуждение.

### Сетка под группы

Число метрик в группе должно делиться на число колонок, иначе в конце ряда
остаётся пустая ячейка и раздел выглядит недоделанным. На дашборде это решено
группировкой **по типу показателя**: 16 базовых метрик = 4 группы по 4 = ровно
4 колонки. Исключение — группа «Лояльность» (с 2026-09-05 одна карточка «Доля
чеков с картой»: владелец свернул четыре карточки лояльности в одну с вкладками,
неполный ряд принят осознанно; 2026-09-04 их было 4).

### Единая высота контролов

`--control-h: 44px` — селект, кнопки-пилюли, круглые стрелки, кнопки экспорта.

`.controls-row` выравнивает группы по нижнему краю (`align-items: flex-end`),
поэтому **любой контрол выше одной строки разводит подписи групп по разным
уровням**. Всё, что должно стоять в строке панели (включая бейджи), кладётся
внутрь неё, а не под неё.

> **Ловушка:** правило вида `.controls-row .control-group:not(.x)` — это три
> класса, и оно побеждает однокласcовое `.control-group-period`. Переопределять
> такое правило одним классом бесполезно: нужно исключать группу через `:not()`
> либо поднимать специфичность. Именно на этом панель периода получала чужую
> ширину и рвалась на два ряда.
>
> **Ловушка 2:** `flex-grow` перебивает заданный `width`. Круглая кнопка с
> `width: 44px` внутри flex-контейнера растянется на пол-строки, если ей достанется
> `flex: 1` — нужен `flex: 0 0 auto`.

### Шапка фильтров (одна полоса)

Группа связанных контролов оформляется как ОДИН элемент: общая рамка, а внутри
контролы без своих рамок, разделённые вертикальными линиями.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ⌂ Все заведения ▾ │ ‹  ▤ Август 2026  1—12 авг ▾  › │        Excel  PDF │
└──────────────────────────────────────────────────────────────────────────┘
```

```css
.filter-bar { position: relative; display: flex; align-items: stretch;
              height: 56px; border: 1px solid var(--border-color);
              border-radius: 14px; background: var(--bg-secondary); }
.fb-item    { border: none; background: transparent; padding: 0 18px; }
.fb-item:hover { background: var(--bg-primary); }
.fb-divider { width: 1px; margin: 13px 0; background: var(--border-color); }
.fb-spacer  { flex: 1; }          /* отбивает второстепенные действия вправо */
```

`position: relative` обязателен: выпадающие списки позиционируются `absolute`
относительно полосы и должны лежать ВНУТРИ неё, иначе уезжают вниз страницы.

**Подпись контрола = название + уточнение.** Крупным — что выбрано
(«Август 2026»), мелким серым — какие это числа («1—12 авг»). Так контрол
отвечает и на вопрос «что», и на вопрос «сколько», не требуя второй строки.

### Выпадающий список / нижний лист

Один компонент, две раскладки: на десктопе выпадашка 272px у своего триггера,
на телефоне — лист снизу во всю ширину с ручкой.

```css
.fb-menu      { position: absolute; top: calc(100% + 6px);
                left: var(--fb-menu-left, 0); width: 272px; padding: 6px;
                border-radius: 14px; box-shadow: var(--shadow-lg); }
.fb-menu-item { display: flex; gap: 10px; padding: 9px 12px; border-radius: 9px; }
.fb-menu-hint { margin-left: auto; color: var(--text-tertiary); }
.fb-menu-item.active { background: var(--accent-light); }   /* текст --accent-hover */

@media (max-width: 768px) {
  .fb-menu { position: fixed; left: 0; right: 0; bottom: 0; width: auto;
             border-radius: 22px 22px 0 0;
             padding-bottom: calc(14px + env(safe-area-inset-bottom, 0px)); }
  .fb-grab { display: block; width: 38px; height: 4px; }   /* ручка листа */
}
```

Неприменимый пункт **гасится** (`:disabled`, opacity .35), а не убирается: список
не должен «прыгать» при переключении вкладок. Причина — в `title`.

**Выбор из списка вместо переключателя.** Если вариантов больше трёх-четырёх или
у каждого есть уточнение (диапазон дат), список компактнее и понятнее сегментов:
в строке остаётся один контрол, а выбор занимает один клик.

### Нижняя таб-панель (мобильный)### Нижняя таб-панель (мобильный)

```css
.bottom-tabs { position: fixed; bottom: 0; display: flex;
               background: var(--bg-secondary);
               border-top: 1px solid var(--border-color);
               padding-bottom: calc(14px + env(safe-area-inset-bottom, 0px)); }
.bt-item.active { color: var(--accent); }
```

Контейнер страницы получает `padding-bottom` под её высоту, иначе панель накрывает
контент. `env(safe-area-inset-bottom)` обязателен — иначе на iPhone панель уезжает
под системный индикатор.

### Таблица

```css
table {
    width: 100%;
    border-collapse: collapse;
}

thead {
    border-bottom: 2px solid var(--border-color);
}

th {
    text-align: left;
    padding: 12px 16px;
    font-weight: 600;
    font-size: 0.8rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

td {
    padding: 16px;
    border-bottom: 1px solid var(--border-color);
}

tr:hover {
    background: var(--bg-tertiary);
}
```

### Badge (статусы ABC/XYZ)

```css
.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

/* ABC цвета */
.badge.aaa, .badge.aab, .badge.aac { background: var(--success); color: white; }
.badge.aba, .badge.abb, .badge.abc { background: var(--accent); color: white; }
.badge.baa, .badge.bab, .badge.bac { background: var(--warning); color: white; }
.badge.ccc { background: var(--danger); color: white; }

/* XYZ цвета */
.badge.x { background: var(--success); color: white; }
.badge.y { background: var(--accent); color: white; }
.badge.z { background: var(--danger); color: white; }
```

### Tooltip

```css
.tooltip-wrapper {
    position: relative;
    display: inline-block;
}

.tooltip {
    visibility: hidden;
    opacity: 0;
    position: absolute;
    bottom: 125%;
    left: 50%;
    transform: translateX(-50%);
    background: var(--bg-secondary);
    padding: 12px 16px;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    box-shadow: 0 4px 12px var(--shadow);
    font-size: 0.85rem;
    transition: opacity 0.2s ease;
}

.tooltip-wrapper:hover .tooltip {
    visibility: visible;
    opacity: 1;
}
```

---

## Layout

### Container

```css
.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 40px 20px;
}
```

### Сетка карточек

```css
.metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
}

/* Адаптивность */
@media (max-width: 1400px) { grid-template-columns: repeat(3, 1fr); }
@media (max-width: 1024px) { grid-template-columns: repeat(2, 1fr); }
@media (max-width: 640px) { grid-template-columns: 1fr; }
```

### Отступы (Spacing)

```css
--spacing-xs: 6px;
--spacing-sm: 12px;
--spacing-md: 20px;
--spacing-lg: 32px;
--spacing-xl: 48px;
--spacing-xxl: 64px;
```

---

## Анимации

### Переходы

```css
transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);  /* fast */
transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);   /* base */
```

### Hover-эффекты

```css
/* Подъём карточки */
transform: translateY(-2px);

/* Тень */
box-shadow: 0 4px 12px rgba(26, 26, 26, 0.08);

/* Масштаб для компактных элементов */
transform: scale(1.02);
```

### Spinner

```css
@keyframes spin {
    to { transform: rotate(360deg); }
}

.loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--border-color);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
```

---

## Адаптивность

### Breakpoints

| Breakpoint | Значение | Что меняется |
|------------|----------|--------------|
| Mobile | `≤768px` | мобильная разметка дашборда (`.mv-mobile`), нижняя таб-панель, шапка фильтров в две строки |
| Tablet | `≤1024px` | 2 колонки в сетках |
| Desktop | `≤1400px` | 3 колонки в сетках |
| Large | `>1400px` | 4 колонки, max-width контейнер |

> Основной брейкпоинт кода — **768px**. Каркас страницы (шапка фильтров, нижняя
> таб-панель) переключается в `base.css`, адаптив контента — в `mobile.css`.
> Каркас лежит в base.css намеренно: недоехавший отдельный файл отдавал бы
> телефону десктопную полосу фильтров, из которой контролы вылетают за экран.
> JS брейкпоинт больше не дублирует — переключение чисто CSS-ное.

### Две версии разметки вместо одной адаптивной

Экран метрик дашборда рисуется **дважды** — `.mv-desktop` и `.mv-mobile` — и
переключается медиазапросом. Так сделано потому, что мобильная версия это не
«та же сетка в одну колонку», а другая информационная структура (сводка + аккордеоны).

Обязательное условие: обе версии строятся из **одних** данных (`analytics.buildStats`),
иначе цифры на телефоне и на десктопе разъедутся.

### Mobile-first правила

1. Таблицы — горизонтальный скролл
2. Карточки — на всю ширину
3. Кнопки — 100% ширины
4. Шрифты — на 10-15% меньше

---

## Theme Toggle

Переключение тем через атрибут на `<html>`:

```html
<html data-theme="dark">
```

```css
[data-theme="dark"] {
    /* Тёмные переменные */
}
```

---

## Changelog

### 2026-09-05 — Группа «Лояльность» — одна карточка

**Что:** четыре карточки лояльности свёрнуты в «Долю чеков с картой» с вкладками
(решение владельца); ряд группы неполный, правило «делится на число колонок»
для этой группы не действует.

### 2026-09-04 — Сетка под группы: 20 метрик = 5 групп по 4

**Что:** на дашборде появилась пятая группа «Лояльность» (4 метрики); правило
«число метрик в группе делится на число колонок» сохранено.

### 2026-04-01 — Создание дизайн-системы

**Что:** Документирование дизайн-системы на основе dashboard.html

**Почему:** Требовалось создать единый источник истины для новых страниц

**Файлы:**
- `.claude/docs/design-system.md` (создан)
- `static/dashboard/styles/*.css` (документированы)

**Как применять:**
1. При создании новой страницы использовать компоненты из этого документа
2. Не изобретать новые стили — использовать существующие переменные
3. Для новых компонентов расширять эту систему, а не дублировать

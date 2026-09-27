# Project Principles

## 1. Deterministic Calculations

All calculations must be **transparent** and **reproducible**:

- No magic numbers — every constant explained
- Formulas documented in plain language
- Same input → same output always
- Rounding rules explicit
- Edge cases described

**UI requirement:** Where possible, show the formula/calculation to users (tooltips, help text, breakdown).

**Пояснения расчётов — свёрнуты по умолчанию** (решение владельца 2026-09-27):
всё, что объясняет, как получено число (формулы, пороги, правила групп, оговорки,
диагностика), прячется за стрелкой-раскрывашкой «Как считается» (`<details>`) рядом
с тем блоком, который объясняет. На экране по умолчанию — только числа и выводы.

- Прозрачность не теряется: текст пояснения целиком на странице, в один клик.
- Интерфейс минимальный: абзацы пояснений не удлиняют страницу и не отвлекают.
- Раскрывашка стоит у своего блока (карточка, таблица, график), а не общим списком
  внизу страницы.
- Не прячем: единицы измерения, подписи осей и колонок, короткую подпись под
  числом («за 7 дней», «по закупке») — без них число читается неверно.

---

## 2. Documentation First

Documentation is written **alongside** code changes, not after.

### Every change documents:
| What | Why | Where | Impact |
|------|-----|-------|--------|
| Feature/bug/fix | Business/technical reason | Files/modules | What breaks if changed wrong |

### Every module doc (`docs/*.md`) has:
```markdown
## Что это
## Файлы
## Как работает (с примерами и формулами)
## Changelog
```

---

## 3. Changelog in Every Session

**At the end of each coding session**, update the changelog:

1. Open `docs/CHANGELOG.md` (create if missing)
2. Add entry: `### YYYY-MM-DD — <session goal>`
3. List changes:
   - What was changed
   - Why
   - Files affected

---

## File Structure

```
.claude/
├── CLAUDE.md          ← this file (project principles)
├── INDEX.md           ← index of all docs with status
└── context.md         ← quick context for Claude

docs/                  ← Source of truth (модульная документация)
├── overview.md        ← architecture, tech stack
├── PROJECT_STRUCTURE.md ← дерево репозитория
├── <module>.md        ← один файл на модуль (dashboard, employee, taps, ...)
├── lessons.md         ← баги и паттерны (Problem→Cause→Solution)
├── CHANGELOG.md       ← session-by-session log
├── guides/            ← человеко-ориентированные инструкции (deploy, bartenders, ...)
├── technical/         ← техсправочники iiko API, mapping, sync flow
├── changelog/         ← исторические записи фиксов (заморожены)
└── archive/           ← устаревшее
```

**iiko API спецификации:** локальная копия — `docs/iiko-api/` (все статьи раздела
`api-documentations` портала, оглавление в `docs/iiko-api/INDEX.md`). Источник истины — портал
`ru.iiko.help` (движок ClickHelp); пересинхронизация: `py -3 scripts/fetch_iiko_api_docs.py`.
Markdown напрямую с портала:
`https://ru.iiko.help/helper/articles/{раздел}/{slug}/?action=getMarkdown`
(раздел напр. `api-documentations`; slug — последний сегмент `#!`-URL). Список статей —
`https://ru.iiko.help/sitemaps/sitemap_publication_{раздел}.xml`.

**Где что лежит:**
- Модульные .md (overview, dashboard, employee, lessons и т.д.) — в корневом `docs/`.
- `.claude/` хранит только индекс и принципы (CLAUDE.md/INDEX.md/context.md).
- `menu_tool/` — отдельное локальное приложение, его доки в `menu_tool/README.md`.

---

## Enforcement

Before finishing any task:
- [ ] Documentation updated for changed modules
- [ ] CHANGELOG.md entry added
- [ ] INDEX.md reflects current state

---

## MCP: всё, что есть в интерфейсе, доступно ИИ-агентам

Решение владельца (2026-09-27): все данные и действия веб-сервиса доступны его
ИИ-агентам по MCP (`/mcp`, см. `docs/mcp.md`). Поэтому:

- **Новый API-маршрут = новый инструмент.** Добавил `/api/...` — опиши его
  `ToolSpec` в `core/mcp/tools/<домен>.py` (content, stocks, analytics, staff)
  или внеси в `EXCLUDED` того же модуля с причиной. Иначе падает
  `tests/test_mcp_coverage.py`, а с ним и автодеплой.
- **Изменил параметры маршрута** — поправь схему инструмента: тесты доменов
  сверяют поля схемы с тем, что маршрут читает.
- Инструмент вызывает тот же маршрут, что страница (`core/mcp/bridge.py`):
  бизнес-логику для агента не дублировать.

---

## Style Rules

**No emojis in code or UI** — никогда не использовать смайлы/эмодзи в:
- Коде (Python, JavaScript, HTML, CSS)
- Тексте интерфейса (кнопки, заголовки, подписи)
- Документации (кроме личных заметок)

Исключение: контент, генерируемый пользователем, или внешние API.

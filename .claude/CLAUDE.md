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

## Графики в Telegram — только через сайт

Решение владельца (2026-10-18): любой график, который уходит в Telegram (бот
@MCPkulturabot), отправляется MCP-инструментом `common_chart_send` — он есть в каждом
коннекторе kultura (в Claude Code: `mcp__kultura__common_chart_send` или
`mcp__kultura-<раздел>__common_chart_send`). Сайт сам рисует картинку и ставит под ней
кнопку «Открыть интерактивно» (мини-приложение, `docs/tg-miniapp.md`).

- **Свою PNG-картинку не рисовать и не отправлять**, даже если умеешь: у неё нет кнопки,
  владелец не откроет цифры.
- Описание графика: вид (`rating`, `periods`, `stack`, `days`), заголовок, категории,
  серии с точными числами из инструментов, источник и время данных — схема в описании
  инструмента.
- `chat_id` — чат, откуда пришёл вопрос; не знаешь — не передавай (уйдёт в чат отчётов
  владельца).
- Инструмент вернул ошибку — перескажи её владельцу дословно (там сказано, что поправить)
  и не подменяй своей картинкой. Инструмента нет в списке — скажи владельцу, что агента
  надо перезапустить: список инструментов читается при запуске.

---

## Бот @MCPkulturabot — в репозитории

Решение владельца (2026-10-19): бот @MCPkulturabot — папка `kultura_bot/` этого репозитория,
работает на Claude API на **отдельном сервере в Амстердаме** (`kultura_bot/engine/`, служба
`kultura-bot`; `docs/kultura-bot.md`). Сайт стоит в России, API Anthropic оттуда недоступен:
на сервер сайта ничего, что зовёт Claude API, не добавлять и прокси к Anthropic не заводить.
Данные бот берёт у сайта по MCP, настройки и привязки — по `/api/bot/*`. Всё, кроме
секретов, — здесь:

- инструкции бота — `kultura_bot/prompts/bot.md`, общие правила агентов — `prompts/agent.md`,
  агенты — `kultura_bot/agents/*.md`, модель, лимиты, расход и графики — `kultura_bot/settings.py`;
- секреты (токен бота, ключ Anthropic) — только страница `/admin/mcp`, раздел «Бот»: репозиторий
  публичный, в файлы их не класть; на сервере бота — только ключ сервера
  (`/etc/kultura-bot.env`, пишет команда установки со страницы);
- просят поменять поведение бота — правь эти файлы (PR -> слияние в `main`): сервер бота сам
  сверяется с GitHub раз в 2 минуты и перезапускается с новой версией;
- `kultura_bot/engine/` не импортирует код сайта (`core`, `routes`, Flask): на сервер бота
  ставится только папка `kultura_bot/` и её зависимости (проверяет `tests/test_kultura_bot.py`).

---

## Style Rules

**No emojis in code or UI** — никогда не использовать смайлы/эмодзи в:
- Коде (Python, JavaScript, HTML, CSS)
- Тексте интерфейса (кнопки, заголовки, подписи)
- Документации (кроме личных заметок)

Исключение: контент, генерируемый пользователем, или внешние API.

# Project Principles

## 1. Deterministic Calculations

All calculations must be **transparent** and **reproducible**:

- No magic numbers — every constant explained
- Formulas documented in plain language
- Same input → same output always
- Rounding rules explicit
- Edge cases described

**UI requirement:** Where possible, show the formula/calculation to users (tooltips, help text, breakdown).

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
├── CLAUDE.md          ← this file
├── INDEX.md           ← all docs with status
├── docs/
│   ├── overview.md    ← architecture, tech stack
│   ├── <module>.md    ← one file per module
│   ├── lessons.md     ← bugs & patterns (Problem→Cause→Solution)
│   └── CHANGELOG.md   ← session-by-session log
```

---

## Enforcement

Before finishing any task:
- [ ] Documentation updated for changed modules
- [ ] CHANGELOG.md entry added
- [ ] INDEX.md reflects current state

---

## Style Rules

**No emojis in code or UI** — никогда не использовать смайлы/эмодзи в:
- Коде (Python, JavaScript, HTML, CSS)
- Тексте интерфейса (кнопки, заголовки, подписи)
- Документации (кроме личных заметок)

Исключение: контент, генерируемый пользователем, или внешние API.

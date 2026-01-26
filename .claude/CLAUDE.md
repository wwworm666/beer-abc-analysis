# Documentation for Artem

For every project, write detailed documentation that explains the whole project in plain language.

## What to write

Explain:
- **Technical architecture** — how the system is designed and why
- **Codebase structure** — how files and folders are organized, how the various parts connect to each other
- **Technology choices** — what we're using and the reasoning behind each decision
- **Lessons learned**:
  - Bugs we ran into and how we fixed them
  - Potential pitfalls and how to avoid them in the future
  - New technologies/patterns discovered
  - How good engineers think and work
  - Best practices demonstrated in this project

## How to write

**Make it engaging to read.** Don't make it sound like boring technical documentation or a textbook.

- Use analogies and anecdotes to make concepts understandable and memorable
- Be specific with examples from the actual codebase
- Include code snippets where they clarify explanations
- Write like you're explaining to a friend, not writing a manual

## File structure

Documentation lives in `.claude/` with a modular structure. Each module gets its own file.

```
.claude/
├── CLAUDE.md              ← these instructions
├── INDEX.md               ← MAIN FILE: hierarchy of all docs with links
└── docs/
    ├── overview.md        ← project architecture, technologies, "why"
    ├── employee.md        ← Employee Dashboard module
    ├── analytics.md       ← ABC/XYZ analysis module
    ├── dashboard.md       ← Plan/Fact dashboard module
    ├── taps.md            ← Taps management module
    └── lessons.md         ← bugs, patterns, "aha moments"
```

## INDEX.md — the main file

This is the entry point. Contains:
- Tree of all documents with links
- Brief description of each module (1-2 lines)
- Status: ✅ current, 📝 TODO, ⚠️ outdated

## Rules

1. **One module = one file**
   - Don't mix Employee and Taps in one file
   - If a module grows too big — split into subfiles

2. **Naming**: lowercase with dashes (`employee-compare.md`, `abc-xyz.md`)

3. **Every file must have**:
   - `## Что это` — what this module does (2-3 sentences)
   - `## Файлы` — which code files belong to this module
   - `## Как работает` — how it works, diagrams, examples
   - `## Changelog` — history of changes

4. **lessons.md is special**
   - All bugs, traps, patterns go here
   - Format: Problem → Cause → Solution
   - Update on every non-trivial fix

## Maintenance

- When you change a module → update its doc + INDEX.md
- When you add a new module → create file + add to INDEX.md
- When you fix an interesting bug → add to lessons.md

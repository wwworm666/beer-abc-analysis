# 📚 Документация проекта

Добро пожаловать в документацию системы управления барами!

---

## 🎯 Быстрый старт

| Документ | Описание |
|----------|----------|
| [📖 README.md](../README.md) | Главная страница проекта |
| [🚀 DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) | (legacy Render) Руководство по деплою — актуальный деплой через Docker Compose на Selectel VPS (https://beerkultura.ru) |
| [💾 RENDER_DISK_SETUP.md](RENDER_DISK_SETUP.md) | (legacy) Настройка Render Disk — на Selectel это host mount `/kultura` |

---

## 👥 Для пользователей

| Документ | Для кого |
|----------|----------|
| [🍺 ИНСТРУКЦИЯ_ДЛЯ_БАРМЕНОВ.md](ИНСТРУКЦИЯ_ДЛЯ_БАРМЕНОВ.md) | Барменов - как работать с кранами |

---

## 🛠️ Для разработчиков

### Основные документы:

- [README.md](../README.md) - Архитектура и структура (Selectel VPS + Docker)
- [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) - (legacy Render) Workflow деплоя
- [RENDER_DISK_SETUP.md](RENDER_DISK_SETUP.md) - (legacy) Работа с данными; на Selectel это host volume `/kultura`

### Структура приложения:

\`\`\`
app.py                  # Главное приложение
core/                   # Бизнес-логика
  ├── taps_manager.py   # Управление кранами
  ├── abc_analysis.py   # ABC-анализ
  ├── xyz_analysis.py   # XYZ-анализ
  └── iiko_api.py       # Интеграция с iiko
templates/              # HTML
static/                 # CSS, JS
\`\`\`

---

## 📦 Архив

Старые документы находятся в [archive/](archive/)

---

## 🔗 Полезные ссылки

- **GitHub репозиторий**: https://github.com/wwworm666/beer-abc-analysis
- **Прод**: https://beerkultura.ru (Selectel VPS, 139.100.200.92)
- **Render Dashboard** (legacy, rollback): https://dashboard.render.com
- **iiko API**: https://api-ru.iiko.services/

---

## 📞 Поддержка

При проблемах:

1. Проверить [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) → Устранение проблем
2. Проверить логи контейнера: `docker compose logs -f` (или Render Dashboard, если rollback)
3. Проверить что host volume \`/kultura\` примонтирован в контейнер

---

**Обновлено:** 2 ноября 2025

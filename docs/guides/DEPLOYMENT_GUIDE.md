# 🚀 Руководство по развертыванию и обновлению

> **АКТУАЛЬНЫЙ ДЕПЛОЙ — Selectel VPS (Docker Compose + Caddy), https://beerkultura.ru.**
> Этот документ описывает устаревший Render-флоу и оставлен как rollback-страховка
> (есть `render.yaml` в репо). Для текущего деплоя см. `docker-compose.yml`,
> `Dockerfile`, `Caddyfile` и `.env.example` в корне репозитория.

---

## 📋 Оглавление

- [Первоначальная настройка](#первоначальная-настройка)
- [Обновление кода](#обновление-кода)
- [Управление данными кранов](#управление-данными-кранов)
- [Устранение проблем](#устранение-проблем)

---

## 🆕 Первоначальная настройка

### Шаг 1: Подготовка репозитория

\`\`\`bash
# Fork или clone репозитория
git clone https://github.com/wwworm666/beer-abc-analysis.git
cd beer-abc-analysis
\`\`\`

### Шаг 2: Создание Web Service на Render

1. **Зайти на** [render.com](https://render.com)
2. **New** → **Web Service**
3. **Connect** GitHub репозиторий
4. **Настройки:**

| Параметр | Значение |
|----------|----------|
| Name | \`beer-abc-analysis\` |
| Environment | \`Python 3\` |
| Build Command | \`pip install -r requirements.txt\` |
| Start Command | \`gunicorn app:app\` |
| Instance Type | \`Free\` или \`Starter\` |

5. **Environment Variables:**

\`\`\`bash
IIKO_API_LOGIN=ваш_логин
IIKO_API_PASSWORD=ваш_пароль
IIKO_ORGANIZATION_ID=ваш_id
\`\`\`

6. **Create Web Service**

### Шаг 3: Создание Render Disk

1. **Dashboard** → **Storage** → **New Disk**
2. **Настройки:**

| Параметр | Значение |
|----------|----------|
| Name | \`kultura-taps-data\` |
| Mount Path | \`/kultura\` |
| Size | \`1 GB\` |

3. **Create Disk**
4. **Подключить** к Web Service (Disks → Attach)

### Шаг 4: Инициализация данных

После первого деплоя, зайти в **Render Shell**:

\`\`\`bash
# Проверить что диск примонтирован
ls -la /kultura

# Если нужно, создать начальный файл
cp data/taps_data.json.example /kultura/taps_data.json

# Проверить что приложение использует диск (в Logs)
# Должно быть: [INFO] Используется Render Disk: /kultura/taps_data.json
\`\`\`

✅ **Готово!** Приложение работает.

---

## 🔄 Обновление кода

### Простой процесс:

\`\`\`bash
# 1. Изменить код локально
# 2. Закоммитить
git add .
git commit -m "Описание изменений"

# 3. Запушить в GitHub
git push origin main

# 4. Render автоматически задеплоит!
\`\`\`

### Автоматический деплой:

- Render отслеживает ветку \`main\`
- При любом \`git push\` начинается новый деплой
- Занимает 2-5 минут
- **Данные кранов сохраняются!** (они на /kultura диске)

### Ручной деплой:

**Render Dashboard** → ваш сервис → **Manual Deploy**

Опции:
- **Deploy latest commit** - быстрый деплой (~2 мин)
- **Clear build cache & deploy** - полная пересборка (~5 мин)

---

## 💾 Управление данными кранов

### Где хранятся данные:

\`\`\`
/kultura/taps_data.json  ← Постоянный Render Disk
\`\`\`

### Скачать историю кранов:

**Render Shell:**

\`\`\`bash
# Весь файл
cat /kultura/taps_data.json

# Только события за сегодня
cat /kultura/taps_data.json | grep '"timestamp": "2025-11-02'

# Количество событий за сегодня
cat /kultura/taps_data.json | grep -c '"timestamp": "2025-11-02'
\`\`\`

Скопировать вывод → Сохранить локально как \`.json\` файл.

### Бэкап данных:

**Render Shell:**

\`\`\`bash
# Создать бэкап
cp /kultura/taps_data.json /kultura/taps_backup_$(date +%Y%m%d).json

# Посмотреть все бэкапы
ls -lh /kultura/taps_backup_*.json

# Восстановить из бэкапа
cp /kultura/taps_backup_20251102.json /kultura/taps_data.json
\`\`\`

### Автоматический бэкап (опционально):

Настроить через **Render Cron Jobs** или **Scheduled Tasks**.

---

## 🛠️ Устранение проблем

### Проблема: Данные кранов не сохраняются

**Проверка:**

1. **Logs** → Найти строку:
   \`\`\`
   [INFO] Используется Render Disk: /kultura/taps_data.json
   \`\`\`

2. Если видите:
   \`\`\`
   [INFO] Используется локальный путь: data/taps_data.json
   \`\`\`
   
   **Проблема:** Диск не примонтирован!

**Решение:**

1. **Dashboard** → **Disks** → Убедиться что диск создан
2. **Attach disk** к Web Service
3. **Redeploy** сервис

### Проблема: Приложение не запускается

**Проверка логов:**

\`\`\`
Render Logs → Events → Посмотреть ошибки
\`\`\`

**Частые причины:**

- ❌ Неправильные Environment Variables
- ❌ Ошибка в \`requirements.txt\`
- ❌ Синтаксическая ошибка в коде

**Решение:**

1. Проверить Environment Variables
2. Проверить что \`git push\` прошёл успешно
3. Откатиться на предыдущий коммит если нужно

### Проблема: Сайт показывает старые данные

**Причина:** Кэш браузера

**Решение:**

- Ctrl+F5 (жёсткое обновление)
- Или открыть в режиме инкогнито

### Проблема: После деплоя пропали краны

**НЕ ДОЛЖНО ПРОИСХОДИТЬ!**

Если произошло:

1. **Shell** → Проверить:
   \`\`\`bash
   ls -la /kultura/taps_data.json
   cat /kultura/taps_data.json | head -50
   \`\`\`

2. Если файл пустой - восстановить из бэкапа
3. Если файла нет - проверить что диск подключен

---

## 🔐 Безопасность

### Environment Variables:

- **НЕ коммитить** в git!
- Хранить только в Render Dashboard
- Использовать через \`os.environ.get()\`

### Данные кранов:

- **НЕ в git** (в \`.gitignore\`)
- Только на Render Disk \`/kultura\`
- Делать бэкапы периодически

---

## 📊 Мониторинг

### Где смотреть логи:

**Render Dashboard** → ваш сервис → **Logs**

### Важные строки в логах:

\`\`\`
✅ [INFO] Используется Render Disk: /kultura/taps_data.json
✅  * Running on http://0.0.0.0:10000
❌ [ERROR] ...
\`\`\`

### Проверка здоровья:

1. Открыть сайт - должен загрузиться
2. \`/taps\` - должны показываться краны
3. Логи - нет ошибок

---

## 📝 Чек-лист деплоя

### Перед изменениями:

- [ ] Сделать бэкап данных кранов
- [ ] Убедиться что код работает локально (опционально)
- [ ] Проверить что \`.gitignore\` не пропускает лишнее

### После git push:

- [ ] Дождаться \`Deploy live\` в Render Events
- [ ] Проверить логи на ошибки
- [ ] Открыть сайт - проверить работоспособность
- [ ] Проверить что краны на месте

---

## 🆘 Контакты

При критических проблемах:

1. **Render Shell** → Проверить состояние
2. **Logs** → Найти ошибку
3. **Откатиться** на предыдущий коммит:
   \`\`\`bash
   git revert HEAD
   git push origin main
   \`\`\`

---

## 📚 Дополнительно

- [README.md](README.md) - Общее описание проекта
- [docs/RENDER_DISK_SETUP.md](docs/RENDER_DISK_SETUP.md) - Детальная настройка диска
- [docs/ИНСТРУКЦИЯ_ДЛЯ_БАРМЕНОВ.md](docs/ИНСТРУКЦИЯ_ДЛЯ_БАРМЕНОВ.md) - Для барменов

---

**Дата обновления:** 2 ноября 2025  
**Версия:** 2.0

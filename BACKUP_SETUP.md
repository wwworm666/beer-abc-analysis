# Настройка автоматических бэкапов

## Вариант 1: Ручной бэкап (ПРОСТОЙ)

Когда проект работает и ты хочешь сохранить состояние:

```bash
# 1. Открой терминал в папке проекта
cd "c:\Users\1\Documents\GitHub\beer-abc-analysis"

# 2. Запусти скрипт бэкапа
backup.bat
```

Готово! Создастся тег `backup-2025-11-15` и отправится на GitHub.

---

## Вариант 2: Автоматический бэкап (РЕКОМЕНДУЮ)

### Шаг 1: Открыть Task Scheduler

1. Нажми `Win + R`
2. Введи `taskschd.msc`
3. Нажми Enter

### Шаг 2: Создать задачу

1. Справа нажми **"Create Task"** (Создать задачу)
2. На вкладке **"General"**:
   - Name: `Beer ABC Backup`
   - Description: `Автоматический бэкап проекта`
   - ✅ Поставь галку **"Run whether user is logged on or not"**
   - ✅ Поставь галку **"Run with highest privileges"**

### Шаг 3: Настроить триггер

1. Перейди на вкладку **"Triggers"**
2. Нажми **"New"**
3. Настрой расписание:
   - **Daily** (каждый день)
   - Start: `22:00` (10 вечера)
   - Recur every: `1` days
   - ✅ Enabled
4. Нажми **OK**

### Шаг 4: Настроить действие

1. Перейди на вкладку **"Actions"**
2. Нажми **"New"**
3. Настрой:
   - Action: `Start a program`
   - Program/script: `C:\Users\1\Documents\GitHub\beer-abc-analysis\backup.bat`
   - Start in: `C:\Users\1\Documents\GitHub\beer-abc-analysis`
4. Нажми **OK**

### Шаг 5: Дополнительные настройки

1. Перейди на вкладку **"Conditions"**:
   - ❌ Убери галку **"Start the task only if the computer is on AC power"**

2. Перейди на вкладку **"Settings"**:
   - ✅ **"Allow task to be run on demand"** (чтобы можно было запустить вручную)
   - ✅ **"Run task as soon as possible after a scheduled start is missed"**

3. Нажми **OK**

---

## Проверка работы

### Запустить бэкап вручную:

1. В Task Scheduler найди задачу `Beer ABC Backup`
2. Правой кнопкой → **Run**
3. Проверь что появился файл `backup_log.txt`

### Посмотреть все бэкапы:

```bash
cd "c:\Users\1\Documents\GitHub\beer-abc-analysis"
git tag -l "backup-*"
```

Вывод:
```
backup-2025-11-15
backup-2025-11-16
backup-2025-11-17
```

---

## Восстановление из бэкапа

### Вариант 1: Посмотреть код из бэкапа

```bash
# Посмотреть файл из бэкапа
git show backup-2025-11-15:app.py
```

### Вариант 2: Вернуться к бэкапу

```bash
# ОСТОРОЖНО! Это удалит все текущие изменения
git checkout backup-2025-11-15
```

### Вариант 3: Создать ветку из бэкапа

```bash
# Безопасный способ - создать новую ветку
git checkout -b restore-from-backup backup-2025-11-15
```

---

## Очистка старых бэкапов

Через 6 месяцев можно удалить старые теги:

```bash
# Удалить тег локально
git tag -d backup-2025-05-15

# Удалить тег на GitHub
git push origin :refs/tags/backup-2025-05-15
```

---

## Частота бэкапов

**Рекомендации:**

- **Каждый день в 22:00** - если активно работаешь
- **Каждую неделю** - если редко меняешь код
- **Перед деплоем** - ОБЯЗАТЕЛЬНО (запусти `backup.bat` вручную)

---

## Проблемы и решения

### "Access denied" при создании задачи

Запусти Task Scheduler от имени администратора.

### Скрипт не запускается

Проверь что Git установлен и доступен в PATH:
```bash
git --version
```

### Бэкап не пушится на GitHub

Проверь что настроена аутентификация Git:
```bash
git config --global user.name
git config --global user.email
```

---

## Логи бэкапов

Все запуски записываются в файл `backup_log.txt`:

```
15.11.2025 22:00:05 - Backup completed
16.11.2025 22:00:03 - Backup completed
17.11.2025 22:00:07 - Backup completed
```

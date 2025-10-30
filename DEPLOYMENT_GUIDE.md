# 🚀 Инструкция по развертыванию обновлений на сервер

## ⚠️ КРИТИЧЕСКИ ВАЖНО!

Файл `data/taps_data.json` содержит **ВСЕ данные сотрудников** о подключенных кранах и историю.

При выгрузке обновлений на сервер **НЕ ПЕРЕЗАПИСЫВАЙТЕ** этот файл!

---

## 📋 Процесс обновления сервера

### 1️⃣ Подготовка локально (на вашем компьютере)

```bash
# 1. Проверьте что все изменения закоммичены
git status

# 2. Добавьте изменения (кроме data/taps_data.json - он в .gitignore)
git add .

# 3. Создайте коммит
git commit -m "Описание изменений"

# 4. Отправьте на сервер
git push origin main
```

---

### 2️⃣ На сервере

```bash
# 1. Перейдите в папку проекта
cd /path/to/beer-abc-analysis

# 2. СНАЧАЛА создайте резервную копию данных!
cp data/taps_data.json data/taps_data.json.backup

# 3. Получите обновления
git pull origin main

# 4. ВАЖНО: Восстановите файл с данными если он перезаписался
cp data/taps_data.json.backup data/taps_data.json

# 5. Перезапустите сервер
sudo systemctl restart beer-abc-app
# или
pkill -f "python app.py" && python app.py &
```

---

## 🛡️ Защита данных (уже настроено)

В файле `.gitignore` добавлена строка:
```
data/taps_data.json
```

Это значит, что git **НЕ БУДЕТ** отслеживать изменения в этом файле.

---

## 🔧 Первое развертывание на новом сервере

Если вы разворачиваете проект на новом сервере:

```bash
# 1. Клонируйте репозиторий
git clone <your-repo-url>
cd beer-abc-analysis

# 2. Создайте файл с данными из шаблона
cp data/taps_data.json.example data/taps_data.json

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Запустите сервер
python app.py
```

---

## 📝 Что делать если данные всё же потерялись

### Вариант 1: Восстановление из бэкапа
```bash
# Если вы делали бэкап перед обновлением:
cp data/taps_data.json.backup data/taps_data.json
```

### Вариант 2: Восстановление из git (если файл был случайно добавлен)
```bash
# Посмотрите историю коммитов
git log --all --full-history -- data/taps_data.json

# Восстановите из конкретного коммита
git checkout <commit-hash> -- data/taps_data.json
```

### Вариант 3: Начать с чистого листа
```bash
cp data/taps_data.json.example data/taps_data.json
```

---

## 🔄 Автоматический бэкап (рекомендуется настроить на сервере)

Создайте скрипт `/usr/local/bin/backup-taps-data.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backup/beer-abc"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
cp /path/to/beer-abc-analysis/data/taps_data.json \
   $BACKUP_DIR/taps_data_$DATE.json

# Удаляем бэкапы старше 30 дней
find $BACKUP_DIR -name "taps_data_*.json" -mtime +30 -delete
```

Добавьте в crontab (запуск каждый час):
```bash
crontab -e

# Добавьте строку:
0 * * * * /usr/local/bin/backup-taps-data.sh
```

---

## ✅ Чек-лист перед обновлением

- [ ] Создал бэкап `data/taps_data.json`
- [ ] Проверил что `.gitignore` содержит `data/taps_data.json`
- [ ] Выполнил `git pull` на сервере
- [ ] Проверил что `data/taps_data.json` не перезаписался
- [ ] Перезапустил сервер
- [ ] Проверил что данные на месте (открыл страницу кранов)

---

## 📞 В случае проблем

1. Проверьте бэкапы в `/backup/beer-abc/`
2. Проверьте историю git: `git log --all -- data/taps_data.json`
3. В крайнем случае восстановите из шаблона и попросите барменов заполнить заново

---

**Дата создания:** 30 октября 2025
**Версия:** 1.0

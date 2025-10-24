# Решение проблем

## ❌ Проблема: Ссылка http://localhost:5000/taps не работает

### Причина:
Flask сервер не запущен!

### Решение:
```bash
python app.py
```

Затем откройте браузер на http://localhost:5000/taps

---

## ❌ "ERR_CONNECTION_REFUSED"

### Это значит:
Компьютер не может подключиться к серверу на порту 5000

### Решение:
1. Убедитесь, что выполнили `python app.py` в терминале
2. Убедитесь, что в терминале видна надпись "Running on http://127.0.0.1:5000"
3. Дождитесь полной загрузки приложения (может занять 2-3 секунды)

---

## ❌ "Port 5000 already in use"

### Это значит:
Какое-то другое приложение использует порт 5000

### Решение 1 (Windows):
```bash
# Найти процесс, использующий порт 5000
netstat -ano | findstr :5000

# Если что-то найдется, закройте то приложение вручную
# или переключитесь на другой порт
```

### Решение 2 - Используйте другой порт:

Отредактируйте **app.py**, найдите в конце файла:
```python
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)  # <- измените 5000
```

Измените на:
```python
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)  # <- новый порт
```

Затем запустите и откройте: http://localhost:5001/taps

---

## ❌ "ModuleNotFoundError: No module named 'flask'"

### Это значит:
Flask не установлен

### Решение:
```bash
pip install flask
```

или установите ВСЕ зависимости сразу:
```bash
pip install -r requirements.txt
```

---

## ❌ "ModuleNotFoundError: No module named 'app'"

### Это значит:
Вы находитесь не в папке проекта

### Решение:
```bash
# Перейдите в папку проекта
cd c:\12\beer-abc-analysis

# Затем запустите
python app.py
```

---

## ❌ Интерфейс загружается, но краны не видны

### Это значит:
JavaScript не может загрузить данные

### Решение:
1. Откройте консоль браузера: **F12 → Console**
2. Посмотрите на красные ошибки (они начинаются с "Error")
3. Проверьте Network вкладку (F12 → Network)
   - Убедитесь, что запросы к `/api/taps/bars` возвращают статус 200
4. Перезагрузите страницу: **Ctrl+Shift+Delete** (очистить кеш) → **Ctrl+F5**

---

## ❌ "Cannot GET /taps"

### Это значит:
Flask приложение запущено, но маршрут /taps не найден

### Решение:
1. Убедитесь, что у вас новая версия `app.py` с добавленным кодом
2. Проверьте, что в `app.py` есть строка:
   ```python
   @app.route('/taps')
   def taps():
       return render_template('taps.html')
   ```
3. Проверьте, что файл `templates/taps.html` существует

---

## ❌ Данные не сохраняются

### Это значит:
Данные не записываются в `data/taps_data.json`

### Решение:
1. Создайте папку `data`:
   ```bash
   mkdir data
   ```

2. Убедитесь, что папка имеет права на запись:
   ```bash
   # Linux/Mac
   chmod 755 data

   # Windows - просто убедитесь, что папка не защищена
   ```

3. Проверьте, что файл создался:
   ```bash
   ls data/taps_data.json  # Linux/Mac
   dir data\taps_data.json # Windows
   ```

---

## ❌ Ошибка "UnicodeEncodeError" в консоли

### Это значит:
Проблема с кодировкой символов (русский язык)

### Решение:
Это НЕ критическая ошибка! Приложение работает нормально.
Ошибка появляется только в консоли, но не влияет на функциональность.

Если хотите избежать:
```bash
# Запустите с правильной кодировкой (Windows)
chcp 65001
python app.py
```

---

## ❌ "Debugger PIN" сообщение

### Это значит:
Flask работает в режиме отладки (debug mode)

### Это нормально!
Это просто предупреждение для разработчиков.
Ваше приложение работает правильно.

Если хотите отключить debug mode:
В `app.py` измените:
```python
app.run(debug=True, ...)  # <- измените True на False
```

На:
```python
app.run(debug=False, ...)
```

---

## ❌ Браузер показывает старую версию интерфейса

### Это значит:
Браузер использует кеш

### Решение:
Очистить кеш браузера:
```
Ctrl+Shift+Delete  (на большинстве браузеров)
```

или

```
Ctrl+H → Очистить данные → Все файлы → Очистить
```

Потом перезагрузить страницу: **Ctrl+F5**

---

## ❌ "Not found: /templates/taps.html"

### Это значит:
Файл `templates/taps.html` не найден

### Решение:
Проверьте структуру папок:
```
beer-abc-analysis/
├── app.py
├── core/
│   └── taps_manager.py
└── templates/
    └── taps.html  <- должен быть здесь!
```

Если файл находится не в папке `templates`, переместите его:
```bash
mv taps.html templates/
```

---

## ❌ "Address already in use"

То же самое, что "Port 5000 already in use"

Смотрите решение выше.

---

## ❌ Демо-данные не загружаются

### Это значит:
Скрипт `demo_taps_data.py` имеет ошибку

### Решение:
```bash
# Убедитесь, что сервер запущен в другом терминале!
python app.py  # <- в терминале 1

# В другом терминале:
python demo_taps_data.py  # <- в терминале 2
```

Если не работает:
```bash
# Проверьте, что вы в правильной папке
cd c:\12\beer-abc-analysis

# Проверьте, что файл существует
dir demo_taps_data.py  # Windows
ls demo_taps_data.py   # Linux/Mac
```

---

## ✅ Как проверить, что все работает

Откройте новый терминал и выполните:

```bash
# Перейдите в папку проекта
cd c:\12\beer-abc-analysis

# Проверьте импорт
python -c "from app import app; print('OK')"

# Проверьте API
python << EOF
from app import app
with app.test_client() as client:
    response = client.get('/api/taps/bars')
    print(f'Status: {response.status_code}')
    if response.status_code == 200:
        print('OK - API works!')
EOF
```

Если обе команды выдали "OK", значит все работает!

---

## 📞 Контрольный чеклист перед стартом

- [ ] Python 3.7+ установлен (`python --version`)
- [ ] Зависимости установлены (`pip install -r requirements.txt`)
- [ ] Папка `data` существует (`mkdir data`)
- [ ] Файл `templates/taps.html` существует
- [ ] Файл `core/taps_manager.py` существует
- [ ] Порт 5000 свободен (`netstat -ano | findstr :5000` = пусто)

Если все ✓, выполните:
```bash
python app.py
```

Откройте: **http://localhost:5000/taps**

---

## 🎓 Интерпретация ошибок

| Сообщение об ошибке | Что означает | Решение |
|---|---|---|
| `ERR_CONNECTION_REFUSED` | Сервер не запущен | `python app.py` |
| `Port 5000 already in use` | Порт занят | Используйте порт 5001 или закройте приложение |
| `ModuleNotFoundError: flask` | Flask не установлен | `pip install flask` |
| `Cannot GET /taps` | Маршрут не найден | Проверьте `app.py` |
| `FileNotFoundError` | Файл не найден | Проверьте структуру папок |
| `UnicodeEncodeError` | Проблема с кодировкой | Не критично, игнорируйте |
| Пустой интерфейс | API не загружает данные | Откройте F12 → Console, смотрите ошибки |

---

## 🆘 Если ничего не помогает

1. **Перезагрузитесь** (⚡ самое мощное решение!)
2. Удалите папку `data` и создайте заново
3. Удалите файл `__pycache__` и `.pyc` файлы
4. Переустановите зависимости:
   ```bash
   pip install --upgrade -r requirements.txt
   ```
5. Начните с нуля - перейдите в папку проекта и запустите заново

---

## 💡 Быстрые команды для диагностики

```bash
# Проверить Python версию
python --version

# Проверить Flask
python -c "import flask; print(f'Flask {flask.__version__}')"

# Проверить структуру папок
tree  # Linux/Mac
dir   # Windows

# Проверить процессы на порту 5000
netstat -ano | findstr :5000  # Windows
lsof -i :5000                 # Linux/Mac

# Очистить кеш Python
rm -rf __pycache__  # Linux/Mac
rmdir /s __pycache__  # Windows

# Переустановить зависимости
pip install --force-reinstall -r requirements.txt
```

---

Если у вас все еще есть вопросы, посмотрите:
- **RUN_SERVER.md** - как запустить сервер
- **START_HERE.md** - начало работы
- **TAPS_QUICK_START.md** - быстрый старт

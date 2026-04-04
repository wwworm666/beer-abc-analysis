# Установка агента MeshCentral

## Быстрая установка (автоматически)

Откройте **PowerShell от имени администратора** и выполните:

```powershell
# Скачать и установить агент
$url = "https://103.85.115.227/meshservice?id=1"
$output = "$env:TEMP\meshagent64.exe"
Invoke-WebRequest -Uri $url -OutFile $output
Start-Process -FilePath $output -ArgumentList "-fullinstall" -Wait
```

---

## Пошаговая установка (вручную)

### Шаг 1: Скачать агента

**Вариант A — Прямая ссылка:**
1. Откройте в браузере: `https://103.85.115.227/meshservice?id=1`
2. Файл скачается в папку "Загрузки"

**Вариант B — Через веб-интерфейс:**
1. Откройте: `https://103.85.115.227`
2. Войдите в систему (логин/пароль администратора)
3. Перейдите в **"My Devices"**
4. Нажмите на группу устройств (например, **"All Devices"**)
5. Нажмите **"Add Devices"** → **"Download Agent"**
6. Сохраните файл `meshagent64-xxxx.exe`

### Шаг 2: Установить агента

1. **Откройте PowerShell от имени администратора:**
   - Нажмите `Win + X`
   - Выберите **"Windows PowerShell (администратор)"** или **"Терминал (администратор)"**

2. **Перейдите в папку загрузок:**
   ```powershell
   cd C:\Users\%USERNAME%\Downloads
   ```

3. **Установите агент (замените имя файла на ваше):**
   ```powershell
   .\meshagent64-xxxx.exe -fullinstall
   ```

   Или через проводник:
   - Правый клик на файле → **"Запуск от имени администратора"**

### Шаг 3: Проверить установку

```powershell
# Проверка статуса службы
Get-Service "Mesh Agent Service"

# Или через exe
& "C:\Program Files\Mesh Agent\MeshAgent.exe" -state
```

Должно показать: `Status: Running`

---

## Проверка в веб-интерфейсе

1. Откройте: `https://103.85.115.227`
2. Войдите в систему
3. Перейдите в **"My Devices"**
4. Ваше устройство должно появиться в списке (через 10-30 секунд)

---

## Управление агентом

### Команды PowerShell:

```powershell
# Проверка статуса
Get-Service "Mesh Agent Service"

# Остановить службу
Stop-Service "Mesh Agent Service"

# Запустить службу
Start-Service "Mesh Agent Service"

# Перезапустить службу
Restart-Service "Mesh Agent Service"

# Удалить агента
& "C:\Program Files\Mesh Agent\MeshAgent.exe" -uninstall
```

### Команды через exe-файл:

```cmd
# Показать статус
"C:\Program Files\Mesh Agent\MeshAgent.exe" -state

# Перезапустить
"C:\Program Files\Mesh Agent\MeshAgent.exe" restart

# Удалить
"C:\Program Files\Mesh Agent\MeshAgent.exe" -uninstall

# Полное удаление (файлы + служба)
"C:\Program Files\Mesh Agent\MeshAgent.exe" -fulluninstall
```

---

## Решение проблем

### Агент не устанавливается

**Ошибка "Не найдена указанная процедура":**
- Установите Visual C++ Redistributable:
  ```
  https://aka.ms/vs/17/release/vc_redist.x64.exe
  ```
- Перезагрузите ПК

**Ошибка "Access Denied":**
- Запустите PowerShell **от имени администратора**

### Агент не подключается к серверу

**Проверьте подключение:**
```powershell
Test-NetConnection 103.85.115.227 -Port 443
```
Должно показать: `TcpTestSucceeded : True`

**Проверьте брандмауэр:**
```powershell
# Временно отключить для теста
netsh advfirewall set allprofiles state off

# После теста включить обратно
netsh advfirewall set allprofiles state on
```

### Устройство не появляется в веб-интерфейсе

1. Подождите 30-60 секунд
2. Обновите страницу (F5)
3. Проверьте логи агента:
   ```powershell
   Get-EventLog -LogName Application -Source "Mesh Agent" -Newest 20
   ```
   Или файл логов:
   ```
   C:\Program Files\Mesh Agent\logs\meshagent.log
   ```

---

## Требования к системе

- **ОС:** Windows 7/8/10/11 или Windows Server 2012+
- **Архитектура:** x64 (64-bit)
- **Права:** Администратор (для установки)
- **Сеть:** Доступ к серверу на порт 443 (HTTPS)

---

## Контакты сервера

- **Адрес:** `https://103.85.115.227`
- **Порт:** 443 (HTTPS)
- **WebSocket:** wss://103.85.115.227

---

## Файлы агента

После установки файлы находятся в:
```
C:\Program Files\Mesh Agent\
├── MeshAgent.exe          # Основной файл
├── MeshAgent64.dll        # Библиотека
├── logs\                  # Логи
└── config.msh             # Конфигурация
```

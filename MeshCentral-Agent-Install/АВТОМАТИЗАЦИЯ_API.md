# MeshCentral - Автоматизация через API и командную строку

## 📋 Содержание

1. [MeshCmd - локальная утилита](#meshcmd---локальная-утилита)
2. [MeshCtrl.js - серверная утилита](#meshctrljs---серверная-утилита)
3. [REST API](#rest-api)
4. [WebSocket API](#websocket-api)
5. [Примеры скриптов](#примеры-скриптов)

---

## MeshCmd - локальная утилита

**MeshCmd** — утилита командной строки для управления MeshCentral с локального ПК.

### Установка MeshCmd

**Скачать с сервера:**
```
https://103.85.115.227/meshcmd?id=1
```

**Или скопировать из установленного агента:**
```
C:\Program Files\Mesh Agent\MeshCmd.exe
```

### Базовое использование

#### Подключение к серверу

```cmd
MeshCmd.exe ConnectServer --url wss://103.85.115.227 --loginuser "wwworm37@gmail.com" --loginpass "ВАШ_ПАРОЛЬ"
```

#### Получить список устройств

```cmd
MeshCmd.exe GetDeviceList
```

**Вывод:**
```
Device ID: abc123def456
Name: PC-BUH
Status: online
Last Connect: 2026-03-30 10:30:00

Device ID: xyz789ghi012
Name: PC-DIR
Status: offline
Last Connect: 2026-03-29 18:00:00
```

#### Выполнить команду на удалённом ПК

```cmd
:: Синтаксис
MeshCmd.exe Dispatch --deviceid [DEVICE_ID] --meshcmd RunCommand --command "[КОМАНДА]"

:: Пример - ipconfig
MeshCmd.exe Dispatch --deviceid abc123def456 --meshcmd RunCommand --command "ipconfig /all"

:: Пример - получить информацию о системе
MeshCmd.exe Dispatch --deviceid abc123def456 --meshcmd RunCommand --command "systeminfo"

:: Пример - перезагрузка
MeshCmd.exe Dispatch --deviceid abc123def456 --meshcmd RunCommand --command "shutdown /r /t 0"
```

#### Отправить файл

```cmd
MeshCmd.exe SendFile --deviceid [DEVICE_ID] --source "C:\local\file.txt" --destination "C:\remote\file.txt"
```

#### Скачать файл

```cmd
MeshCmd.exe GetFile --deviceid [DEVICE_ID] --source "C:\remote\file.txt" --destination "C:\local\file.txt"
```

#### Подключение к рабочему столу

```cmd
:: Только просмотр
MeshCmd.exe Desktop --deviceid [DEVICE_ID] --viewonly

:: С управлением
MeshCmd.exe Desktop --deviceid [DEVICE_ID]
```

#### Подключение к терминалу

```cmd
MeshCmd.exe Terminal --deviceid [DEVICE_ID]
```

---

## MeshCtrl.js - серверная утилита

**MeshCtrl.js** — утилита на сервере для управления через CLI.

### Подключение

```bash
# SSH на сервер
ssh root@103.85.115.227

# Перейти в директорию MeshCentral
cd /opt/meshcentral
```

### Команды

#### Получить список пользователей

```bash
node node_modules/meshcentral/meshctrl.js ListUsers
```

#### Получить список устройств

```bash
node node_modules/meshcentral/meshctrl.js ListDevices
```

#### Получить информацию об устройстве

```bash
node node_modules/meshcentral/meshctrl.js ShowDevice --id [DEVICE_ID]
```

#### Добавить пользователя

```bash
node node_modules/meshcentral/meshctrl.js AddUser --name "user@example.com" --pass "Password123!" --email "user@example.com"
```

#### Удалить пользователя

```bash
node node_modules/meshcentral/meshctrl.js RemoveUser --name "user@example.com"
```

#### Сбросить пароль пользователя

```bash
node node_modules/meshcentral/meshctrl.js ResetPassword "user@example.com" "NewPassword123!"
```

#### Экспорт базы данных

```bash
node node_modules/meshcentral/meshctrl.js ExportData --output backup.json
```

#### Импорт базы данных

```bash
node node_modules/meshcentral/meshctrl.js ImportData --input backup.json
```

#### Отправить команду на устройство

```bash
node node_modules/meshcentral/meshctrl.js RunCommand --id [DEVICE_ID] --command "ipconfig /all"
```

#### Перезагрузить устройство

```bash
node node_modules/meshcentral/meshctrl.js Restart --id [DEVICE_ID]
```

#### Выключить устройство

```bash
node node_modules/meshcentral/meshctrl.js Shutdown --id [DEVICE_ID]
```

---

## REST API

MeshCentral предоставляет REST API для автоматизации.

### Базовый URL

```
https://103.85.115.227
```

### Аутентификация

**Получение токена:**

```bash
curl -k -X POST https://103.85.115.227/auth \
  -H "Content-Type: application/json" \
  -d '{"username":"wwworm37@gmail.com","password":"ВАШ_ПАРОЛЬ"}'
```

**Ответ:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires": 3600
}
```

### API Endpoints

#### Получить список устройств

```bash
curl -k -X GET https://103.85.115.227/api/devices \
  -H "Authorization: Bearer TOKEN"
```

#### Получить информацию об устройстве

```bash
curl -k -X GET https://103.85.115.227/api/devices/DEVICE_ID \
  -H "Authorization: Bearer TOKEN"
```

#### Выполнить команду

```bash
curl -k -X POST https://103.85.115.227/api/devices/DEVICE_ID/command \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command": "ipconfig /all"}'
```

#### Перезагрузить устройство

```bash
curl -k -X POST https://103.85.115.227/api/devices/DEVICE_ID/restart \
  -H "Authorization: Bearer TOKEN"
```

#### Получить статус устройства

```bash
curl -k -X GET https://103.85.115.227/api/devices/DEVICE_ID/status \
  -H "Authorization: Bearer TOKEN"
```

---

## WebSocket API

Для реального времени можно использовать WebSocket.

### Подключение

```javascript
const WebSocket = require('ws');

const ws = new WebSocket('wss://103.85.115.227', {
  headers: {
    'Authorization': 'Bearer TOKEN'
  }
});

ws.on('open', () => {
  console.log('Connected!');

  // Подписка на события устройства
  ws.send(JSON.stringify({
    action: 'subscribe',
    device: 'DEVICE_ID'
  }));
});

ws.on('message', (data) => {
  console.log('Received:', data.toString());
});
```

### События

| Событие | Описание |
|---------|----------|
| `deviceConnected` | Устройство подключилось |
| `deviceDisconnected` | Устройство отключилось |
| `commandResult` | Результат выполнения команды |
| `desktopFrame` | Кадр рабочего стола |
| `terminalData` | Данные терминала |

---

## Примеры скриптов

### PowerShell - проверка всех устройств

```powershell
# MeshCentral Device Checker
$server = "https://103.85.115.227"
$username = "wwworm37@gmail.com"
$password = "ВАШ_ПАРОЛЬ"

# Получить список устройств
$devices = & "C:\Program Files\Mesh Agent\MeshCmd.exe" GetDeviceList

foreach ($device in $devices) {
    $lines = $device -split "`n"
    $name = ($lines | Select-String "Name:").Line.Split(":")[1].Trim()
    $status = ($lines | Select-String "Status:").Line.Split(":")[1].Trim()

    Write-Host "$name - $status" -ForegroundColor $(if($status -eq "online"){"Green"}else{"Red"})

    if ($status -eq "offline") {
        # Отправить уведомление
        Write-Warning "Device $name is offline!"
    }
}
```

### PowerShell - массовое выполнение команды

```powershell
# Массовое выполнение команды на всех устройствах
$command = "ipconfig /all"
$outputDir = "C:\MeshCentral-Output"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

# Получить список устройств
$devices = & "C:\Program Files\Mesh Agent\MeshCmd.exe" GetDeviceList

foreach ($device in $devices) {
    $lines = $device -split "`n"
    $name = ($lines | Select-String "Name:").Line.Split(":")[1].Trim()
    $deviceId = ($lines | Select-String "Device ID:").Line.Split(":")[1].Trim()
    $status = ($lines | Select-String "Status:").Line.Split(":")[1].Trim()

    if ($status -eq "online") {
        Write-Host "Выполнение на $name..."

        # Выполнить команду
        $result = & "C:\Program Files\Mesh Agent\MeshCmd.exe" Dispatch `
            --deviceid $deviceId `
            --meshcmd RunCommand `
            --command $command

        # Сохранить результат
        $result | Out-File "$outputDir\$name-ipconfig.txt"
    }
}

Write-Host "Готово! Результаты в $outputDir"
```

### Batch - быстрая проверка

```cmd
@echo off
chcp 65001 >nul
echo Проверка устройств MeshCentral
echo ==============================
echo.

"C:\Program Files\Mesh Agent\MeshCmd.exe" GetDeviceList | findstr /C:"Name:" /C:"Status:"

echo.
echo ==============================
pause
```

### Python - мониторинг устройств

```python
#!/usr/bin/env python3
import subprocess
import re
from datetime import datetime

def get_devices():
    """Получить список устройств"""
    result = subprocess.run(
        ['C:\\Program Files\\Mesh Agent\\MeshCmd.exe', 'GetDeviceList'],
        capture_output=True,
        text=True,
        encoding='utf-8'
    )

    devices = []
    current = {}

    for line in result.stdout.split('\n'):
        if 'Device ID:' in line:
            if current:
                devices.append(current)
            current = {'id': line.split(':')[1].strip()}
        elif 'Name:' in line:
            current['name'] = line.split(':')[1].strip()
        elif 'Status:' in line:
            current['status'] = line.split(':')[1].strip()

    if current:
        devices.append(current)

    return devices

def main():
    print(f"=== MeshCentral Device Monitor ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    devices = get_devices()

    online = 0
    offline = 0

    for device in devices:
        status = device.get('status', 'unknown')
        name = device.get('name', 'Unknown')

        if status == 'online':
            print(f"✓ {name} - ONLINE")
            online += 1
        else:
            print(f"✗ {name} - OFFLINE")
            offline += 1

    print()
    print(f"Total: {len(devices)} | Online: {online} | Offline: {offline}")

if __name__ == '__main__':
    main()
```

### Bash (на сервере) - ежедневный отчёт

```bash
#!/bin/bash
# daily-report.sh

DATE=$(date +%Y-%m-%d)
REPORT="/var/log/meshcentral/daily-report-$DATE.txt"

cd /opt/meshcentral

echo "MeshCentral Daily Report" > $REPORT
echo "Date: $DATE" >> $REPORT
echo "========================" >> $REPORT
echo "" >> $REPORT

# Список устройств
echo "Devices:" >> $REPORT
node node_modules/meshcentral/meshctrl.js ListDevices >> $REPORT

# Список пользователей
echo "" >> $REPORT
echo "Users:" >> $REPORT
node node_modules/meshcentral/meshctrl.js ListUsers >> $REPORT

# Отправить по email
mail -s "MeshCentral Daily Report $DATE" admin@example.com < $REPORT
```

### Cron - запуск каждый день в 8:00

```bash
# Добавить в crontab
crontab -e

# Строка:
0 8 * * * /opt/meshcentral/daily-report.sh
```

---

## Интеграция с другими системами

### Telegram уведомление

```python
import requests

def send_telegram(message):
    bot_token = "YOUR_BOT_TOKEN"
    chat_id = "YOUR_CHAT_ID"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }

    requests.post(url, json=data)

# Использование
send_telegram("⚠️ Device PC-BUH is offline!")
```

### Email уведомление (PowerShell)

```powershell
Send-MailMessage `
  -From "meshcentral@company.com" `
  -To "admin@company.com" `
  -Subject "MeshCentral Alert" `
  -Body "Device is offline!" `
  -SmtpServer "smtp.company.com"
```

### Slack уведомление

```bash
#!/bin/bash
webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"🔴 Device offline!"}' \
  $webhook_url
```

---

## Безопасность API

### Хранение токенов

**Не храните пароли в скриптах!** Используйте:

**Windows Credential Manager:**
```powershell
# Сохранить пароль
cmdkey /generic:MeshCentral /user:wwworm37@gmail.com /pass:PASSWORD

# Использовать в скрипте
$cred = Get-StoredCredential -Target "MeshCentral"
```

**Переменные окружения:**
```bash
# Установить
export MESHCENTRAL_USER="wwworm37@gmail.com"
export MESHCENTRAL_PASS="PASSWORD"

# Использовать
curl -u $MESHCENTRAL_USER:$MESHCENTRAL_PASS ...
```

### Ограничение доступа

Настройте IP Filtering в config.json:

```json
{
  "settings": {
    "ipFilter": {
      "enabled": true,
      "allowedIps": ["192.168.1.0/24", "10.0.0.0/8"],
      "blockedIps": []
    }
  }
}
```

---

## Ссылки

- **MeshCmd документация:** https://ylianst.github.io/MeshCentral/meshcmd/
- **API документация:** https://meshcentral.com/docs/
- **Примеры скриптов:** https://github.com/Ylianst/MeshCentral/tree/master/scripts

---

**Версия:** 1.0
**Дата:** 2026-03-30

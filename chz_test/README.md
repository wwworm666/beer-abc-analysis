# Честный ЗНАК API — Полное руководство

Рабочий клиент ЧЗ API: аутентификация через УКЭП + получение сроков годности кодов маркировки пива.

## Содержание

1. [Что нужно на бар-ПК](#1-что-нужно-на-бар-пк)
2. [Настройка удалённого доступа (SSH)](#2-настройка-удалённого-доступа-ssh)
3. [Установка Python](#3-установка-python)
4. [Настройка ЧЗ клиента](#4-настройка-чз-клиента)
5. [Аутентификация — как это работает](#5-аутентификация--как-это-работает)
6. [Команды](#6-команды)
7. [Интеграция в основной проект](#7-интеграция-в-основной-проект)
8. [Известные проблемы и решения](#8-известные-проблемы-и-решения)

---

## 1. Что нужно на бар-ПК

### Оборудование
- **Рутокен ЭЦП 2.0 (или Rutoken ECP)** с установленной УКЭП организации
- USB-порт на бар-ПК (рутокен должен быть вставлен)

### Программное обеспечение
- **CryptoPro CSP 5.0+** — установлен, лицензия активна
  - Проверка: `"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keyset -enum_cont -fqcn`
  - Должен показать контейнер вида `\\.\Aktiv Rutoken ECP 0\<номер>`
- **Python 3.10+** (64-bit)
- **Интернет** — доступ к `markirovka.crpt.ru`

### Учётные данные
- **УКЭП** привязана к организации (ИНН организации должен совпадать с тем, что в сертификате)
- Сертификат должен быть установлен в хранилище пользователя (CurrentUser\My)
- Сертификат должен быть виден через CryptoPro CSP

### Как узнать данные для подключения
На бар-ПК выполни:
```cmd
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keyset -enum_cont -fqcn
```
Запиши имя контейнера — оно понадобится для отладки.

Открой CryptoPro CSP -> Сервис -> Просмотреть сертификат в контейнере -> Выбрать контейнер.
Запиши **отпечаток** (Thumbprint) — строка из 40 hex-символов.

---

## 2. Настройка удалённого доступа (SSH)

### Установка OpenSSH Server на бар-ПК

На бар-ПК (через RDP или физически), PowerShell **от администратора**:

```powershell
# Проверить, установлен ли OpenSSH Server
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'

# Установить
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Запустить службу
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'

# Разрешить в фаерволе (обычно автоматически)
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

### Создание пользователя для SSH

```powershell
# Создать пользователя
New-LocalUser -Name "sshuser" -Password (ConvertTo-SecureString "chz2026" -AsPlainText -Force) -PasswordNeverExpires

# Добавить в группу администраторов (ОБЯЗАТЕЛЬНО для доступа к сертификату)
Add-LocalGroupMember -Group "Администраторы" -Member "sshuser"
```

> **Важно:** Пользователь должен быть в группе Администраторы, иначе csptest.exe не получит доступ к контейнеру Рутокена.

### Подключение с локальной машины

```bash
ssh sshuser@<IP-адрес-бар-ПК>
```

IP бар-ПК можно узнать через Tailscale, ZeroTier, или `ipconfig` на бар-ПК.

### Альтернатива: вход как Администратор

Если есть пароль учётной записи `Администратор`, можно подключаться напрямую:
```bash
ssh Администратор@<IP-адрес-бар-ПК>
```

---

## 3. Установка Python

### Вариант A: Тихая установка через SSH

```powershell
# Скачать установщик
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe" -OutFile "$env:USERPROFILE\Desktop\python-installer.exe"

# Установить (тихо, для всех пользователей, добавить в PATH)
& "$env:USERPROFILE\Desktop\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1

# Подождать 30 секунд, проверить
python --version
```

### Вариант B: Ручная установка

1. Скачать с python.org
2. При установке отметить **"Add Python to PATH"** и **"Install for all users"**
3. Перезапустить cmd

---

## 4. Настройка ЧЗ клиента

### Структура файлов

```
C:\chz_test\
├── chz.py              # Единый скрипт (аутентификация + данные)
├── requirements.txt    # Зависимости (не нужны для работы, только urllib)
└── debug\              # Рабочая папка (токен, подпись, данные)
    ├── token.json
    ├── _data_to_sign.txt
    ├── _signature.txt
    ├── expiration_data.json
    └── expiration_full.json
```

### Конфигурация chz.py

В начале файла `chz.py` нужно указать свои данные:

```python
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"  # свой отпечаток
INN_ORG = "7801630649"          # ИНН организации из сертификата
ORG_NAME = 'ООО "ИНВЕСТАГРО"'   # Название организации
```

### Как узнать отпечаток сертификата

```cmd
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keyset -enum_cont -fqcn
# Записать имя контейнера

"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keyset -container "\\.\Aktiv Rutoken ECP 0\<контейнер>" -info
```

Или через CryptoPro CSP GUI: Сервис -> Просмотреть сертификат -> Подробности -> Отпечаток.

### Как узнать ИНН организации

ИНН указан в сертификате. Его можно увидеть:
- В веб-интерфейсе ЧЗ (личный кабинет)
- В деталях сертификата через CryptoPro CSP
- В учредительных документах организации

---

## 5. Аутентификация — как это работает

### Рабочая комбинация (проверено экспериментально)

**Шаг 1:** Получить challenge от сервера
```
GET https://markirovka.crpt.ru/api/v3/true-api/auth/key
Ответ: {"uuid": "...", "data": "30-символьная строка"}
```

**Шаг 2:** Подписать данные через CryptoPro CSP
```cmd
csptest.exe -sfsign -sign -my "THUMBPRINT" -in data.txt -out sig.txt -base64 -cades_strict -add
```

**КРИТИЧЕСКИ ВАЖНО:**
- **НЕ использовать `-detached`** — с этим флагом сервер возвращает 403
- Флаги `-cades_strict -add` — обязательны
- `-base64` — вывод в base64
- Формат подписи: **присоединённая** (attached), не detached

**Шаг 3:** Отправить подпись на сервер
```
POST https://markirovka.crpt.ru/api/v3/true-api/auth/simpleSignIn
{"uuid": "uuid-из-key", "data": "подпись-base64"}
Ответ: {"token": "eyJ...", "uuid": "..."}
```

**Шаг 4:** Использовать токен
```
Authorization: Bearer eyJ...
```

Токен действует ~10 часов. Скрипт сохраняет его в `debug/token.json` и автоматически обновляет при истечении.

### Почему НЕ работает с `-detached`

Флаг `-detached` создаёт отделённую подпись (signature без данных). Сервер ЧЗ ожидает присоединённую подпись (CAdES Signature), где данные встроены в подпись. С `-detached` сервер не может верифицировать подпись и возвращает 403 "Ошибка авторизации. Код ошибки: 2".

### Формат запроса: v2, НЕ v3

Рабочий формат — v2: `{"uuid": "...", "data": "подпись"}`

Формат v3 (`unitedToken`) НЕ работает для simpleSignIn.

---

## 6. Команды

### Получить/обновить токен
```cmd
cd C:\chz_test
python chz.py token
```

### Проверить организацию в ЧЗ
```cmd
python chz.py participants
```
Показывает статус организации, доступные группы продуктов (beer, nabeer и т.д.)

### Поиск кодов (1 страница, 30 дней)
```cmd
python chz.py search
```

С конкретной даты:
```cmd
python chz.py search 2026-03-01
```

Период:
```cmd
python chz.py search 2026-03-01 2026-04-05
```

### Полный отчёт (все страницы)
```cmd
python chz.py report
```

С периодом:
```cmd
python chz.py report 2026-03-01 2026-04-05
```

Выводит по каждому GTIN: количество кодов, срок годности, дата производства, MOD ID.
Сохраняет:
- `debug/expiration_data.json` — сводка по GTIN
- `debug/expiration_full.json` — все записи

### Удалённый запуск через SSH

С локальной машины (Python + paramiko):
```python
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('IP-бара', username='sshuser', password='chz2026')

stdin, stdout, stderr = client.exec_command(
    'cd /d C:\\chz_test && python chz.py report', timeout=300
)
print(stdout.read().decode('utf-8', errors='replace'))
client.close()
```

---

## 7. Интеграция в основной проект

Импорт функций из chz.py:

```python
from chz import load_token, make_request, CHZ_BASE_URL, INN_ORG

token = load_token()  # автоматически обновит если истёк

# Поиск кодов маркировки
headers = {"Authorization": f"Bearer {token}"}
payload = {
    "page": 0,
    "limit": 100,
    "filter": {
        "productGroups": ["beer"],
        "ownerInn": INN_ORG,
        "introducedDatePeriod": {
            "from": "2026-03-01T00:00:00.000Z",
            "to": "2026-04-05T23:59:59.999Z"
        }
    }
}

status, response = make_request(
    f"{CHZ_BASE_URL_V4}/cises/search",
    method="POST", data=payload, headers=headers
)
```

---

## 8. Известные проблемы и решения

### Проблема: csptest возвращает ErrorCode 0x8009001f

**Причина:** Нет доступа к контейнеру Рутокена.

**Решение:**
1. Убедиться что Рутокен вставлен в USB
2. Запускать от имени Администратора
3. Проверить что пользователь в группе Администраторы
4. Переподключить Рутокен

### Проблема: 403 "Ошибка авторизации. Код ошибки: 2"

**Причина 1:** Используется флаг `-detached`.

**Решение:** Убрать `-detached` из команды csptest.

**Причина 2:** ИНН организации в скрипте не совпадает с ИНН в сертификате.

**Решение:** Проверить INN_ORG в chz.py — должен совпадать с ИНН организации, на которую выдан сертификат.

### Проблема: UnicodeEncodeError на бар-ПК

**Причина:** Windows кодировка cp1251 не поддерживает эмодзи и unicode-символы.

**Решение:** Не использовать эмодзи (✅❌📄) и box-drawing символы (─│┌┐) в print. Заменить на ASCII: `[OK]`, `[ERR]`, `---`.

### Проблема: certutil -store my пустой

**Причина:** Сертификат установлен в другом пользователе или в LocalMachine.

**Решение:**
1. Открыть CryptoPro CSP GUI
2. Сервис -> Просмотреть сертификат в контейнере
3. Выбрать контейнер Рутокена
4. Установить сертификат (если не установлен)

### Проблема: SSH подключается, но csptest не работает

**Причина:** SSH-пользователь не в группе Администраторы.

**Решение:**
```powershell
Add-LocalGroupMember -Group "Администраторы" -Member "sshuser"
```
После этого нужно перелогиниться (выйти и зайти снова).

### Проблема: Python не найден после установки

**Причина:** PATH не обновился в текущей сессии.

**Решение:** Перезапустить cmd или использовать полный путь:
```cmd
"C:\Program Files\Python312\python.exe" chz.py report
```

---

## Changelog

### 2026-04-09 — Рабочая аутентификация ЧЗ

- Найдена рабочая комбинация: `csptest -sfsign -sign` (БЕЗ `-detached`) + v2 формат
- Устранена проблема 403 — флаг `-detached` создавал отделённую подпись, сервер не верифицировал
- Устранены Unicode-ошибки — замена эмодзи и box-drawing на ASCII (cp1251 на Windows)
- Настроен удалённый доступ через SSH (sshuser / Администратор)
- Установлен Python 3.12 на бар-ПК
- Получены данные: 79 кодов, 16 GTIN, за период 2026-03-12 — 2026-04-11

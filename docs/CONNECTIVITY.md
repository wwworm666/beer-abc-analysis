# Подключение к устройствам

## chz_test/ (бар-ПК, 2026-04-06/07)

### Устройство
- **IP:** `100.98.149.108` (KION KVM-30)
- **Имя:** `DESKTOP-E0BLMGC`, пользователь `sshuser` / `chz2026`
- **Сетевые интерфейсы:** 192.168.8.120, 100.98.149.108, 169.254.150.108
- **Порт:** 22 (OpenSSH)

### Сертификат и подпись через КРИПТО-ПРО
- КриптоПро CSP есть в системе
- Подпись через `cryptcp` (есть в `chz_test/cryptcp.x64.exe`)
- Подпись на `Kremlevskaya.pfx` (ГОСТ, срок до 24.01.2027)

### Подпись работает только от имени Администратора
- `sshuser` **НЕ** в группе `Администраторы`
- В группе `Администраторы` — только `Администратор` и `Гость`
- cryptcp требует доступ к хранилищу ключей, которое доступно только `Администратор`
- Попытки логина как `Администратор` / `Administrator` с паролем `Krem2026!` — все FAIL
- Кириллическое имя `Администратор` может некорректно передаваться через SSH password auth
- Учётка `Администратор` активна (net user подтверждает), последний вход 05.04.2026 20:16:33

### Подтверждённые возможности через sshuser
- Подключение по SSH: OK
- Запуск PowerShell скриптов: OK (через pwsh.exe)
- Запуск cryptcp.exe: FAIL — access denied to certificate store
- Доступ к `C:\Users\Администратор\Desktop\КРЕМЛЕВСКАЯ\Kremlevskaya.pfx`: FAIL — access denied
- Добавление в группу администраторов: FAIL — System error 5 (Access denied)
- Чтение `net user Администратор`: OK (информация)
- `net user`: выводит кириллицу с кодировочными артефактами
- Проверка через `whoami /priv`: OK

### Цепочка подписания (отлажена, работает только под Администратором)
1. **GET** `/api/chz/inn/get-auth-data` → uuid, dataToSign, thumbprint, cert
2. Сохранить `data.txt` (UTF-8 без BOM)
3. Подписать cryptcp: `cryptcp.x64.exe -signf -dn "KREMLEVSKAYA" data.txt sign.txt` (или `-detached`)
4. Конвертировать `.sfs`/`.sig` в base64
5. **POST** `/api/chz/inn/auth` → {"uuid": ..., "signature": ...}

### Форматы подписи (протестированы)
- Все форматы .fss/.p7m — FAIL (not valid GOST signature)
- Attached .sfs — FAIL (not valid GOST signature)
- Detached .sfs — FAIL (not valid GOST signature)
- Attached .p7s — FAIL (not valid GOST signature)
- CMS (cryptcp -sign -cades_type CAdES_BES) — FAIL (not valid GOST signature)
- Detached .p7s — FAIL (not valid GOST signature)
- .p7b — FAIL (not valid GOST signature)
- **CAdES-BES .sig (через cryptcp -signf -cades_type CAdES_BES)** — FAIL (not valid GOST signature)

**Вывод:** cryptcp генерирует валидную подпись, но сервер возвращает 500/invalid. Возможные причины:
- Сервер ожидает другой формат (raw signature, custom encoding)
- Нужна подпись именно detached CAdES-BES с конкретной кодировкой
- Проблема в том, что подписывается сырой `dataToSign`, а нужен канонизованный JSON/xml

### Протестированные варианты входа через SSH
| Пользователь | Пароль | Результат |
|---|---|---|
| sshuser | chz2026 | OK (ключ + пароль) |
| Администратор | Krem2026! | FAIL (Authentication failed) |
| Administrator | Krem2026! | FAIL (Authentication failed) |
| DESKTOP-E0BLMGC\Администратор | Krem2026! | FAIL |
| DESKTOP-E0BLMGC\Administrator | Krem2026! | FAIL |

### Привилегии sshuser
- Состоит в группах: `Пользователи`
- **НЕ** в группе `Администраторы`
- `runas /user:Администратор` — FAIL (пустой результат, не работает)
- `net localgroup Администраторы sshuser /add` — FAIL (Access denied)
- Смена пароля Администратора через `net user` — FAIL (Access denied)

### Что нужно для завершения
- Получить доступ к `Администратор` на бар-ПК (добавить sshuser в Администраторы)
- Или запустить test signing из-под Администратора напрямую (RDP)
- Проверить что сервер ожидает — возможно не стандартный cryptcp формат

================
## Бар-10 (в процессе, 2026-04-07)

### Устройство
- **IP:** `100.98.149.104` (KION KVM-30)
- **Имя:** `DESKTOP-777` (или `DESKTOP-425D006`)
- **Пользователи:** `1` / `qwe123`, `Андрей` (RDP)
- **OpenSSH:** есть, но **НЕ отвечает** на порту 22 на момент 07.04.2026

### Доступ
- SSH через sshuser: FAIL — port 22 не отвечает (connect refused)
- RDP через `1` / `qwe123`: OK, **работает**
- RDP через `Андрей` / `qwe123`: FAIL (неверный пароль)

### Сертификат КриптоПро
- Носитель: **Jacarta** (USB-токен)
- Владелец: `ТЮМЕНЕВА О. И.` / Тюменева Ольга Ивановна, ИНН `720333916747`, ORGN 324750000049582
- Срок: **12.12.2024 – 12.12.2025** — ПРОСРОЧЕН
- Серийный номер: `0C900DCD4CD38092D7143AFC5E00`
- Удостоверяющий центр: ООО "Компания "Тензор"
- Невозможно экспортировать приватный ключ без Jacarta

### КриптоПро CSP
- Стандартная установка с ключевым носителем Jacarta
- Подписывать можно только с физическим доступом (вставленный USB токен + КриптоПро CSP)
- `cryptcp` может быть недоступен, нужно проверить

### API сервер
- **Базовый URL:** `http://127.0.0.1:57007`
- **Документация:** `http://127.0.0.1:57007/docs`
- **API:** `/api/chz/inn/get-auth-data` и `/api/chz/inn/auth`
- **Код ошибки:** `NOT_VALID_GOST_SIGNATURE` / HTTP 500 при подписании

### Что делать дальше
- Включить и настроить OpenSSH Server на бар-10
- Проверить/обновить сертификат (просрочен)
- Подключить Jacarta + КриптоПро + cryptcp для автоматизации

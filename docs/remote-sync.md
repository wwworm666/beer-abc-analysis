# Удалённая работа: Сервер → Бар-ПК

**Обновлено:** 2026-04-22
**Метод:** Tailscale (сеть) + OpenSSH (команды) + paramiko (клиент Python)

## Топология

| Компонент | Значение |
|-----------|----------|
| Сервер (этот ПК) | `100.122.143.1` (DESKTOP-55FPVI2) |
| Бар-ПК | `100.98.149.108` (DESKTOP-E0BLMGC) |
| Сеть | Tailscale (tailnet, ping 8ms) |
| Протокол | OpenSSH Server (Windows) + paramiko |
| Учётка на бар-ПК | `Администратор` / пароль из `REMOTE_PASS` env |
| Python на бар-ПК | `C:\Program Files\Python312\python.exe` |
| Скрипты на бар-ПК | `C:\chz_test\chz.py` |

## Как это работает

```
Сервер (paramiko) ──Tailscale(100.98.149.108:22)──→ Бар-ПК (OpenSSH Server)
     │                                                    │
     │  python remote_exec.py cmd "dir C:\chz_test"       │
     │                                                    │
     │  python remote_exec.py push chz.py C:\chz_test\    │
     │  python remote_exec.py pull C:\chz_test\debug\*.json data/
```

## Использование (remote_exec.py)

Требует переменную окружения `REMOTE_PASS` (пароль SSH). `REMOTE_USER` необязателен (по умолчанию: Администратор).

```bash
# Проверить связь
python remote_exec.py status

# Выполнить любую команду
python remote_exec.py cmd "dir C:\chz_test"

# Передать файл
python remote_exec.py push chz_test/chz.py C:\chz_test

# Забрать файл
python remote_exec.py pull C:\chz_test\debug\chz_stock.json chz_test/debug/

# Обновить токен ЧЗ, собрать остатки, скачать chz_stock.json
python remote_exec.py run stock

# Запустить chz.py с произвольными аргументами
python remote_exec.py run report 2026-03-01 2026-04-05
```

## Настройка бар-ПК (выполнено 2026-04-05)

### 1. Установка OpenSSH Server

```powershell
# PowerShell от администратора
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

### 2. Создание пользователя sshuser

```cmd
net user sshuser /add
net user sshuser chz2026
```

### 3. Настройка SSH-ключа

Публичный ключ сервера в `C:\Users\sshuser\.ssh\authorized_keys`:
- Файл создан через `copy con authorized_keys` (Ctrl+Z → Enter)
- НЕ через `echo` — добавляет BOM/доп. символы
- Права: sshuser:(F), SYSTEM:(F)

### Критические нюансы Windows OpenSSH

**sshd_config (`C:\ProgramData\ssh\sshd_config`):**
```
Match Group administrators
   AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
```
Для пользователей из группы administrators sshd ищет ключ в `__PROGRAMDATA__/ssh/administrators_authorized_keys`, НЕ в `~/.ssh/authorized_keys`.

**authorized_keys — права:**
- Файл: только sshuser и SYSTEM имеют полный доступ
- Папка `.ssh`: sshuser владелец
- `echo >` может добавить BOM — использовать `copy con`

**Tailscale SSH:**
- `tailscale ssh` НЕ работает Windows-to-Windows (серверная часть только на Linux/macOS)
- Нужно использовать `ssh user@tailscale-ip` с OpenSSH Server

## Ошибки и решения

### Tailscale SSH → 502 Bad Gateway
**Причина:** Windows Tailscale не поддерживает SSH server mode
**Решение:** Использовать стандартный OpenSSH Server поверх Tailscale сети

### OpenSSH не принимает авторизацию → Permission denied
**Причина:** Файл `authorized_keys` создан через `echo` — добавляет символ новой строки в кодировке, не распознаваемой OpenSSH
**Решение:** `copy con authorized_keys` → вставить ключ → Ctrl+Z → Enter

### Tailscale SSH → Permission denied (key auth)
**Причина:** `Match Group administrators` в sshhd_config перенаправляет поиск ключа
**Решение:** Для обычных пользователей ключ в `~/.ssh/authorized_keys`, для админов — в `C:\ProgramData\ssh\administrators_authorized_keys`

### Права на authorized_keys → отказ
**Причина:** Windows OpenSSH StrictMode требует чтобы файл принадлежал пользователю
**Решение:** `icacls authorized_keys /inheritance:r` + `icacls authorized_keys /grant sshuser:(F)`

### Нет терминала → ввод пароля невозможен
**Причина:** В bash-обёртке Windows `ssh` не может открыть `/dev/tty`
**Решение:** Использовать paramiko (Python библиотека) — не требует терминала

### SMB порты открыты, но подключение отказано
**Причина:** Windows без пароля не принимает анонимные SMB подключения
**Решение:** Использовать SSH вместо SMB

### MeshCentral REST API не работает
**Причина:** Документация в папке — шаблонная, реальный MeshCentral не имеет публичного REST API
**Решение:** MeshCentral — только через веб-интерфейс (ручной)

## Текущее состояние бар-ПК

- Python: `C:\Program Files\Python312\python.exe` (Python 3.12)
- chz_test: `C:\chz_test\chz.py` — актуальный скрипт, загружен через push
- Git репо: НЕ клонировано (скрипты живут в C:\chz_test, не в репо)
- OpenSSH Server: запущен, работает
- Tailscale: подключён, ping работает
- Пользователь SSH: Администратор (подпись csptest.exe требует прав администратора)

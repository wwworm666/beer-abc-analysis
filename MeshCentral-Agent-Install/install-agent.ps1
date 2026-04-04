# MeshCentral Agent Installer
# Запускать от имени администратора!

$ErrorActionPreference = "Stop"

# Цветной вывод
function Write-Info  { Write-Host $args -ForegroundColor Cyan }
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Error_ { Write-Host $args -ForegroundColor Red }

Write-Info "============================================"
Write-Info "  MeshCentral Agent Installer"
Write-Info "============================================"
Write-Info ""

# Проверка прав администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error_ "ОШИБКА: Запустите скрипт от имени администратора!"
    Write-Error_ "Правый клик на файле -> Запуск от имени администратора"
    exit 1
}
Write-Success "[OK] Права администратора подтверждены"

# Адрес сервера
$SERVER_URL = "https://103.85.115.227"
$AGENT_URL = "$SERVER_URL/meshservice?id=1"
$TEMP_DIR = $env:TEMP
$AGENT_PATH = "$TEMP_DIR\meshagent64.exe"
$INSTALL_DIR = "C:\Program Files\Mesh Agent"

Write-Info ""
Write-Info "Сервер: $SERVER_URL"
Write-Info "Папка загрузки: $TEMP_DIR"
Write-Info ""

# Проверка подключения к серверу
Write-Info "Проверка подключения к серверу..."
try {
    $response = Invoke-WebRequest -Uri $SERVER_URL -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Success "[OK] Сервер доступен"
    }
} catch {
    Write-Error_ "[FAIL] Не удалось подключиться к серверу!"
    Write-Error_ "Проверьте подключение к интернету и брандмауэр"
    exit 1
}

# Скачивание агента
Write-Info ""
Write-Info "Скачивание агента..."
try {
    Invoke-WebRequest -Uri $AGENT_URL -OutFile $AGENT_PATH -TimeoutSec 60 -ErrorAction Stop
    Write-Success "[OK] Агент скачан: $AGENT_PATH"
} catch {
    Write-Error_ "[FAIL] Не удалось скачать агента!"
    Write-Error_ $_.Exception.Message
    exit 1
}

# Проверка файла
if (-not (Test-Path $AGENT_PATH)) {
    Write-Error_ "[FAIL] Файл агента не найден!"
    exit 1
}

# Установка агента
Write-Info ""
Write-Info "Установка агента..."
try {
    $process = Start-Process -FilePath $AGENT_PATH -ArgumentList "-fullinstall" -Wait -PassThru -ErrorAction Stop
    if ($process.ExitCode -eq 0) {
        Write-Success "[OK] Агент установлен"
    } else {
        Write-Error_ "[FAIL] Ошибка установки (код: $($process.ExitCode))"
        exit 1
    }
} catch {
    Write-Error_ "[FAIL] Ошибка при установке: $($_.Exception.Message)"
    exit 1
}

# Проверка службы
Write-Info ""
Write-Info "Проверка службы..."
Start-Sleep -Seconds 3
try {
    $service = Get-Service "Mesh Agent Service" -ErrorAction Stop
    if ($service.Status -eq "Running") {
        Write-Success "[OK] Служба запущена: $($service.Status)"
    } else {
        Write-Info "Служба остановлена, запускаем..."
        Start-Service "Mesh Agent Service"
        Write-Success "[OK] Служба запущена"
    }
} catch {
    Write-Error_ "[WARN] Служба не найдена, пробуем альтернативу..."
    try {
        $service = Get-Service "MeshAgent" -ErrorAction Stop
        if ($service.Status -eq "Running") {
            Write-Success "[OK] Служба запущена: $($service.Status)"
        }
    } catch {
        Write-Error_ "[FAIL] Служба не найдена!"
        exit 1
    }
}

# Финальная проверка
Write-Info ""
Write-Info "Финальная проверка..."
Start-Sleep -Seconds 5
try {
    $testResult = Test-NetConnection 103.85.115.227 -Port 443 -InformationLevel Quiet
    if ($testResult) {
        Write-Success "[OK] Подключение к серверу работает"
    } else {
        Write-Error_ "[WARN] Нет подключения к серверу на порт 443"
    }
} catch {
    Write-Error_ "[WARN] Не удалось проверить подключение"
}

Write-Info ""
Write-Info "============================================"
Write-Success "  УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!"
Write-Info "============================================"
Write-Info ""
Write-Info "Проверьте устройство в веб-интерфейсе:"
Write-Info "  $SERVER_URL"
Write-Info ""
Write-Info "Раздел: My Devices"
Write-Info ""

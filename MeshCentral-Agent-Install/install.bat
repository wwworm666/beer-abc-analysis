@echo off
chcp 65001 >nul
title MeshCentral Agent Installer

echo ============================================
echo   MeshCentral Agent Installer
echo ============================================
echo.
echo Сервер: https://103.85.115.227
echo.

:: Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ОШИБКА] Запустите от имени администратора!
    echo Правый клик -^> Запуск от имени администратора
    pause
    exit /b 1
)

echo [OK] Права администратора подтверждены
echo.

:: Скачивание агента
echo Скачивание агента...
powershell -Command "Invoke-WebRequest -Uri 'https://103.85.115.227/meshservice?id=1' -OutFile '%TEMP%\meshagent64.exe'"

if not exist "%TEMP%\meshagent64.exe" (
    echo [ОШИБКА] Не удалось скачать агент!
    pause
    exit /b 1
)

echo [OK] Агент скачан
echo.

:: Установка
echo Установка агента...
"%TEMP%\meshagent64.exe" -fullinstall

echo.
echo ============================================
echo   УСТАНОВКА ЗАВЕРШЕНА!
echo ============================================
echo.
echo Проверьте устройство в веб-интерфейсе:
echo   https://103.85.115.227
echo   Раздел: My Devices
echo.
pause

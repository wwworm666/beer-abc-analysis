@echo off
chcp 65001 >nul
title MeshCentral Agent Uninstaller

echo ============================================
echo   MeshCentral Agent Uninstaller
echo ============================================
echo.

:: Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ОШИБКА] Запустите от имени администратора!
    pause
    exit /b 1
)

echo [OK] Права администратора подтверждены
echo.

:: Проверка существования агента
if exist "C:\Program Files\Mesh Agent\MeshAgent.exe" (
    echo Удаление агента...
    "C:\Program Files\Mesh Agent\MeshAgent.exe" -fulluninstall
    echo.
    echo [OK] Агент удалён
) else (
    echo [INFO] Агент не найден
)

echo.
echo ============================================
echo   УДАЛЕНИЕ ЗАВЕРШЕНО!
echo ============================================
echo.
pause

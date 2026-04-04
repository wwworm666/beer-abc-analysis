@echo off
chcp 65001 >nul
title MeshCentral Agent Status

echo ============================================
echo   MeshCentral Agent Status Checker
echo ============================================
echo.

:: Проверка службы
echo Статус службы:
sc query "Mesh Agent Service" | findstr "SERVICE_NAME STATE"
echo.

:: Проверка подключения к серверу
echo Проверка подключения к серверу (103.85.115.227:443)...
powershell -Command "Test-NetConnection 103.85.115.227 -Port 443 -InformationLevel Quiet"
echo.

:: Проверка процесса
echo Процессы Mesh Agent:
tasklist | findstr "Mesh"
echo.

:: Версия агента
if exist "C:\Program Files\Mesh Agent\MeshAgent.exe" (
    echo Версия агента:
    "C:\Program Files\Mesh Agent\MeshAgent.exe" -info
)

echo.
echo ============================================
pause

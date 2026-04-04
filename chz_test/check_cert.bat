@echo off
echo ========================================
echo ПРОВЕРКА СЕРТИФИКАТОВ И КОНТЕЙНЕРОВ
echo ========================================

echo.
echo 1. Список контейнеров ключей:
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keys -enum

echo.
echo 2. Список сертификатов в хранилище:
"C:\Program Files\Crypto Pro\CSP\certmgr.exe" -list

echo.
echo 3. Проверка конкретного сертификата по отпечатку:
"C:\Program Files\Crypto Pro\CSP\certmgr.exe" -list -thumbprint 2297e52c1066bcaab8a9708a66935e56d9761fc2

echo.
echo 4. Проверка контейнера по имени:
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -keyinfo -cont "2508151514-781421365746"

pause

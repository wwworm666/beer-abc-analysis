@echo off
chcp 65001 >nul
echo Подпись ИНН для ЧЗ API
echo.
echo Команда:
echo "C:\Program Files\Crypto Pro\CSP\csptest.exe" -sfsign -sign -my "2297e52c1066bcaab8a9708a66935e56d9761fc2" -in "C:\Users\1\Desktop\debug\inn.txt" -out "C:\Users\1\Desktop\debug\sig_inn.txt" -base64
echo.
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -sfsign -sign -my "2297e52c1066bcaab8a9708a66935e56d9761fc2" -in "C:\Users\1\Desktop\debug\inn.txt" -out "C:\Users\1\Desktop\debug\sig_inn.txt" -base64
echo.
if %ERRORLEVEL% EQU 0 (
    echo [OK] Podpis sozdana
) else (
    echo [ERROR] Oshibka: %ERRORLEVEL%
)
pause

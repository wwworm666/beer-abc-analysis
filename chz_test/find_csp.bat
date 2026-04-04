@echo off
echo Ищем csptest.exe...
where csptest.exe 2>nul
if %ERRORLEVEL% neq 0 echo Не найдено в PATH

echo.
echo Проверяем стандартные пути:
if exist "C:\Program Files\Crypto Pro\CSP\csptest.exe" echo НАЙДЕН: C:\Program Files\Crypto Pro\CSP\csptest.exe
if exist "C:\Program Files (x86)\Crypto Pro\CSP\csptest.exe" echo НАЙДЕН: C:\Program Files (x86)\Crypto Pro\CSP\csptest.exe

echo.
echo Запуск с полным путём:
"C:\Program Files\Crypto Pro\CSP\csptest.exe" -? 2>&1 | findstr /C:"Crypto" /C:"CSP" /C:"Version"

pause

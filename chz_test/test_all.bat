@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ╔════════════════════════════════════════════════════════════════════════════╗
echo ║  ПОЛНЫЙ ТЕСТ ПОДПИСИ ДЛЯ ЧЕСТНЫЙ ЗНАК API                                  ║
echo ╚════════════════════════════════════════════════════════════════════════════╝

set "CSP=C:\Program Files\Crypto Pro\CSP\csptest.exe"
set "CERT=2297e52c1066bcaab8a9708a66935e56d9761fc2"
set "DEBUG=C:\chz_test\debug"
set "TEMP=%TEMP%"

mkdir "%DEBUG%" 2>nul

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo ШАГ 1: Получение UUID и DATA от ЧЗ API
echo ════════════════════════════════════════════════════════════════════════════

curl -s "https://markirovka.crpt.ru/api/v3/true-api/auth/key" > "%TEMP%\auth_response.json"
type "%TEMP%\auth_response.json"

REM Извлекаем uuid и data из JSON (простой парсинг)
for /f "tokens=2 delims=:" %%a in ('findstr "uuid" "%TEMP%\auth_response.json"') do set "UUID=%%~a"
set "UUID=%UUID:"=%"
set "UUID=%UUID:,=%"
set "UUID=%UUID: =%"

for /f "tokens=2 delims=:" %%a in ('findstr "data" "%TEMP%\auth_response.json"') do set "DATA=%%~a"
set "DATA=%DATA:"=%"
set "DATA=%DATA:,=%"
set "DATA=%DATA: =%"
set "DATA=%DATA:}=%"

echo.
echo UUID: %UUID%
echo DATA: %DATA%

echo %UUID% > "%DEBUG%\01_uuid.txt"
echo %DATA% > "%DEBUG%\02_data.txt"
echo|set /p=%DATA% > "%TEMP%\data_to_sign.txt"

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo ШАГ 2: Тест различных команд подписи
echo ════════════════════════════════════════════════════════════════════════════

echo.
echo --- ТЕСТ 1: -sfsign -sign (присоединённая) ---
%CSP% -sfsign -sign -my "%CERT%" -in "%TEMP%\data_to_sign.txt" -out "%TEMP%\sig1.txt" -base64
if %ERRORLEVEL%==0 (
    echo УСПЕХ!
    type "%TEMP%\sig1.txt" > "%DEBUG%\03_sig1_attached.txt"
) else (echo ОШИБКА %ERRORLEVEL%)

echo.
echo --- ТЕСТ 2: -sfsign -sign -detached (откреплённая) ---
%CSP% -sfsign -sign -detached -my "%CERT%" -in "%TEMP%\data_to_sign.txt" -out "%TEMP%\sig2.txt" -base64
if %ERRORLEVEL%==0 (
    echo УСПЕХ!
    type "%TEMP%\sig2.txt" > "%DEBUG%\04_sig2_detached.txt"
) else (echo ОШИБКА %ERRORLEVEL%)

echo.
echo --- ТЕСТ 3: -sign (простая без -sfsign) ---
%CSP% -sign -my "%CERT%" -in "%TEMP%\data_to_sign.txt" -out "%TEMP%\sig3.txt" -base64
if %ERRORLEVEL%==0 (
    echo УСПЕХ!
    type "%TEMP%\sig3.txt" > "%DEBUG%\05_sig3_simple.txt"
) else (echo ОШИБКА %ERRORLEVEL%)

echo.
echo --- ТЕСТ 4: -hash + подпись хэша ---
%CSP% -hash -in "%TEMP%\data_to_sign.txt" -out "%TEMP%\hash.txt"
if %ERRORLEVEL%==0 (
    echo Хэш создан:
    type "%TEMP%\hash.txt"
    %CSP% -sfsign -sign -my "%CERT%" -hash "%TEMP%\hash.txt" -out "%TEMP%\sig4.txt" -base64
    if %ERRORLEVEL%==0 (
        echo Подпись хэша УСПЕХ!
        type "%TEMP%\sig4.txt" > "%DEBUG%\06_sig4_hash.txt"
    ) else (echo ОШИБКА подписи %ERRORLEVEL%)
) else (echo ОШИБКА хэша %ERRORLEVEL%)

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo ШАГ 3: Проверка созданных файлов
echo ════════════════════════════════════════════════════════════════════════════

echo.
echo Файлы в debug:
dir "%DEBUG%" /b

echo.
echo Содержимое sig1 (attached):
type "%DEBUG%\03_sig1_attached.txt" 2>nul | findstr /v "^$" | more

echo.
echo ════════════════════════════════════════════════════════════════════════════
echo ПАУЗА - проверь файлы в C:\chz_test\debug\
echo ════════════════════════════════════════════════════════════════════════════
pause

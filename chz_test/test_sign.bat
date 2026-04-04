@echo off
chcp 65001 >nul
setlocal

set DATA=TOCJVINHPFCLMSGKRLQGRSWGJAPKUY
set CSP="C:\Program Files\Crypto Pro\CSP\csptest.exe"

echo Данные для подписи: %DATA%
echo.

REM Сохраняем данные в файл
echo|set /p=%DATA%> "%TEMP%\chz_data.txt"

echo ========================================
echo ВАРИАНТ 1: -my с отпечатком
echo ========================================
%CSP% -sign -my "2297e52c1066bcaab8a9708a66935e56d9761fc2" -in "%TEMP%\chz_data.txt" -out "%TEMP%\sig1.txt" -base64
if %ERRORLEVEL% EQU 0 (
    echo УСПЕХ! Подпись:
    type "%TEMP%\sig1.txt"
) else (
    echo ОШИБКА %ERRORLEVEL%
)
echo.

echo ========================================
echo ВАРИАНТ 2: -cont с полным именем
echo ========================================
%CSP% -sign -cont "SCARD\pkcs11_rutoken_ecp_46c444f8\2508151514-781421365746" -in "%TEMP%\chz_data.txt" -out "%TEMP%\sig2.txt" -base64
if %ERRORLEVEL% EQU 0 (
    echo УСПЕХ! Подпись:
    type "%TEMP%\sig2.txt"
) else (
    echo ОШИБКА %ERRORLEVEL%
)
echo.

echo ========================================
echo ВАРИАНТ 3: -provtype 80 -cont
echo ========================================
%CSP% -sign -provtype 80 -cont "2508151514-781421365746" -in "%TEMP%\chz_data.txt" -out "%TEMP%\sig3.txt" -base64
if %ERRORLEVEL% EQU 0 (
    echo УСПЕХ! Подпись:
    type "%TEMP%\sig3.txt"
) else (
    echo ОШИБКА %ERRORLEVEL%
)
echo.

echo ========================================
echo ВАРИАНТ 4: -dn (Distinguished Name)
echo ========================================
%CSP% -sign -dn "CN=АО ""Аналитический Центр"", SN=ВЕРЕЩАГИН, GIVEN=ЕГОР, EMAIL=egais@ffbeer.ru" -in "%TEMP%\chz_data.txt" -out "%TEMP%\sig4.txt" -base64
if %ERRORLEVEL% EQU 0 (
    echo УСПЕХ! Подпись:
    type "%TEMP%\sig4.txt"
) else (
    echo ОШИБКА %ERRORLEVEL%
)
echo.

pause

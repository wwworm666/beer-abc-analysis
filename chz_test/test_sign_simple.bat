@echo off
chcp 65001
setlocal

set "CSP=C:\PROGRA~1\CRYPTO~1\CSP\csptest.exe"
set "CERT=2297e52c1066bcaab8a9708a66935e56d9761fc2"
set "CONT=2508151514-781421365746"
set "DATA=TOCJVINHPFCLMSGKRLQGRSWGJAPKUY"

echo Data: %DATA%
echo|set /p=%DATA%> "%TEMP%\chz_data.txt"

echo.
echo === TEST 1: -my %CERT% ===
%CSP% -sign -my %CERT% -in "%TEMP%\chz_data.txt" -out "%TEMP%\sig1.txt" -base64
if %ERRORLEVEL%==0 echo SUCCESS! & type "%TEMP%\sig1.txt"
if not %ERRORLEVEL%==0 echo FAILED: %ERRORLEVEL%

echo.
echo === TEST 2: -cont SCARD\...\%CONT% ===
%CSP% -sign -cont "SCARD\pkcs11_rutoken_ecp_46c444f8\%CONT%" -in "%TEMP%\chz_data.txt" -out "%TEMP%\sig2.txt" -base64
if %ERRORLEVEL%==0 echo SUCCESS! & type "%TEMP%\sig2.txt"
if not %ERRORLEVEL%==0 echo FAILED: %ERRORLEVEL%

echo.
echo === TEST 3: -provtype 80 -cont %CONT% ===
%CSP% -sign -provtype 80 -cont %CONT% -in "%TEMP%\chz_data.txt" -out "%TEMP%\sig3.txt" -base64
if %ERRORLEVEL%==0 echo SUCCESS! & type "%TEMP%\sig3.txt"
if not %ERRORLEVEL%==0 echo FAILED: %ERRORLEVEL%

pause

@echo off
chcp 65001 >nul

set "CSP=C:\PROGRA~1\CRYPTO~1\CSP\csptest.exe"
set "CERT=2297e52c1066bcaab8a9708a66935e56d9761fc2"
set "DEBUG=C:\chz_test\debug"

mkdir "%DEBUG%" 2>nul

echo STEP 1: Get UUID and DATA from CHZ API
echo =========================================
curl -s "https://markirovka.crpt.ru/api/v3/true-api/auth/key" > "%TEMP%\auth.json"
type "%TEMP%\auth.json"

echo.
echo STEP 2: Create test data file
echo =========================================
echo|set /p=TESTDATA > "%TEMP%\test_data.txt"
type "%TEMP%\test_data.txt"

echo.
echo STEP 3: Test signature commands
echo =========================================

echo.
echo TEST 1: -sfsign -sign (attached)
%CSP% -sfsign -sign -my %CERT% -in "%TEMP%\test_data.txt" -out "%DEBUG%\sig1.txt" -base64
if %ERRORLEVEL%==0 echo OK - see %DEBUG%\sig1.txt
if not %ERRORLEVEL%==0 echo ERROR %ERRORLEVEL%

echo.
echo TEST 2: -sfsign -sign -detached (detached)
%CSP% -sfsign -sign -detached -my %CERT% -in "%TEMP%\test_data.txt" -out "%DEBUG%\sig2.txt" -base64
if %ERRORLEVEL%==0 echo OK - see %DEBUG%\sig2.txt
if not %ERRORLEVEL%==0 echo ERROR %ERRORLEVEL%

echo.
echo TEST 3: -sign (simple)
%CSP% -sign -my %CERT% -in "%TEMP%\test_data.txt" -out "%DEBUG%\sig3.txt" -base64
if %ERRORLEVEL%==0 echo OK - see %DEBUG%\sig3.txt
if not %ERRORLEVEL%==0 echo ERROR %ERRORLEVEL%

echo.
echo TEST 4: -hash then sign hash
%CSP% -hash -in "%TEMP%\test_data.txt" -out "%TEMP%\hash.txt"
if %ERRORLEVEL%==0 (
    echo Hash created
    type "%TEMP%\hash.txt"
    %CSP% -sfsign -sign -my %CERT% -hash "%TEMP%\hash.txt" -out "%DEBUG%\sig4.txt" -base64
    if %ERRORLEVEL%==0 echo Signature OK - see %DEBUG%\sig4.txt
    if not %ERRORLEVEL%==0 echo Sign ERROR %ERRORLEVEL%
) else (echo Hash ERROR %ERRORLEVEL%)

echo.
echo =========================================
echo Check files in %DEBUG%
pause

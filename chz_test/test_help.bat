@echo off
chcp 65001
set "CSP=C:\PROGRA~1\CRYPTO~1\CSP\csptest.exe"

echo ========================================
echo СПРАВКА CSPTEST.EXE
echo ========================================
%CSP% -?

echo.
echo ========================================
echo ДОСТУПНЫЕ КОМАНДЫ
echo ========================================
%CSP% -commands

pause

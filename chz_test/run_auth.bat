@echo off
chcp 65001 >nul
echo ================================================================================
echo CHESTNY ZNAK API AUTH
echo ================================================================================
echo.
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    echo Found py launcher
    set PYTHON=py
    goto :run
)
where python >nul 2>nul
if %ERRORLEVEL%==0 (
    echo Found python
    set PYTHON=python
    goto :run
)
if exist "C:\Python39\python.exe" (
    echo Found Python 3.9
    set PYTHON=C:\Python39\python.exe
    goto :run
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    set PYTHON=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe
    goto :run
)
echo Python not found
pause
exit /b 1
:run
echo Running: %PYTHON%
%PYTHON% "%~dp0chz_auth.py"
pause

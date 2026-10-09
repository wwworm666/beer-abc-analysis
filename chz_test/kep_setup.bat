@echo off
rem Nastroyka KEP dlya chz.py (Chestnyi znak) na bar-PK: dvoinoi shchelchok.
rem Ryadom dolzhny lezhat kep_setup.py i chz.py (naprimer, na fleshke).
cd /d "%~dp0"
set PY="C:\Program Files\Python312\python.exe"
if not exist %PY% set PY=python
%PY% "%~dp0kep_setup.py"
echo.
pause

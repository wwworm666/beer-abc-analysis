@echo off
REM Daily sync script for Windows Task Scheduler
REM Schedule this to run at 6:00 AM daily

cd /d "c:\Users\wwwor\OneDrive\Документы\GitHub\beer-abc-analysis"
python scripts\daily_sync.py 1

echo.
echo Sync completed at %date% %time%

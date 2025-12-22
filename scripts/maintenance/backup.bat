@echo off
REM Автоматический бэкап проекта beer-abc-analysis
REM Запускается через Task Scheduler

cd /d "c:\Users\1\Documents\GitHub\beer-abc-analysis"

REM Получаем текущую дату
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set YEAR=%datetime:~0,4%
set MONTH=%datetime:~4,2%
set DAY=%datetime:~6,2%
set DATE_TAG=%YEAR%-%MONTH%-%DAY%

echo ========================================
echo BACKUP: %DATE_TAG%
echo ========================================

REM Добавляем все изменения
git add -A

REM Создаём коммит (если есть изменения)
git diff-index --quiet HEAD || git commit -m "BACKUP: Автоматический бэкап %DATE_TAG%"

REM Создаём тег
git tag backup-%DATE_TAG% 2>nul

REM Пушим в GitHub
git push origin main
git push origin backup-%DATE_TAG% 2>nul

echo.
echo [OK] Бэкап завершён: backup-%DATE_TAG%
echo ========================================

REM Логируем результат
echo %date% %time% - Backup completed >> backup_log.txt

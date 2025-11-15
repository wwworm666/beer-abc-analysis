@echo off
REM Ежедневное обновление маппинга новых блюд
REM Запускайте этот файл раз в день или добавьте в планировщик задач Windows

echo ============================================================
echo EZHEDNEVNOE OBNOVLENIE MAPPINGA
echo ============================================================
echo.

cd /d %~dp0

echo [1/2] Proverka novyh blyud i avtomaticheskoe dobavlenie...
python auto_add_new_dishes.py

echo.
echo [2/2] Perezapusk servera...
echo Ostanovite server (Ctrl+C) i zapustite snova: python app.py

echo.
echo ============================================================
echo GOTOVO!
echo ============================================================
echo Prover'te fayl NEW_DISHES_FOR_REVIEW.csv
echo.

pause

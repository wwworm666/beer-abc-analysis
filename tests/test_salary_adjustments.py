"""
УСТАРЕЛ (2026-07-31): ручные корректировки ЗП (отпуск/доп доход/вычеты)
выведены из приложения — владелец ведёт эти строки только в Excel-таблице.
Методы get/set_salary_adjustments и API /api/salary/adjustments удалены;
таблица salary_adjustments оставлена в БД (миграции additive-only) — её
сохранность проверяет tests/test_handover_penalties.py.

Актуальные тесты ручного штрафа за кассовую смену (заменившего корректировки):
tests/test_handover_penalties.py. Этот файл можно удалить.
"""

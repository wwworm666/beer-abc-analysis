"""
API страницы расчёта ЗП (/salary): ручной штраф за кассовую смену и экспорт в Excel.

Штраф за кассовую смену — решение владельца по конкретному дню сотрудника
(сумма кассы указана неверно, забыты траты из кассы): премия «передача смены»
(500 ₽) за этот день не платится. Работает поверх автоправила «нет кассы — нет
премии» (с 11.07.2026) и не задваивается с ним: день, уже не оплаченный
автоправилом, повторно не вычитается (routes/employee.py, _manual_penalty_days).
Хранение — shifts.db, handover_cash_penalties (схема v9); каждая простановка/
снятие пишется в журнал графика (schedule_audit).

Ручные корректировки ЗП (отпуск/доп доход/вычеты, схема v8) выведены из
приложения 2026-07-31 — владелец ведёт эти строки только в Excel-таблице;
таблица salary_adjustments оставлена в БД (миграции additive-only).

Экспорт принимает уже посчитанные страницей данные (payload — контракт в
core/salary_export.py) и отдаёт результат в формате таблицы бухгалтерии:
экспорт совпадает с тем, что показывает страница. Два формата, две кнопки:

- `POST /api/salary/export`         -> .xlsx (openpyxl, core/salary_export.py);
- `POST /api/salary/export-gsheet`  -> вкладка в Google Таблице
  (Sheets API, core/salary_gsheet.py).

Строки, формулы и оформление у обоих общие — `core/salary_layout.py`.
"""

import io
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file

from extensions import shifts_mgr
from core.auth_guard import current_user
from core.salary_export import build_salary_workbook
from core.salary_gsheet import GSheetError, GSheetNotConfigured, export_to_gsheet

salary_bp = Blueprint('salary', __name__)

# fullmatch + \Z-семантика: '$' в re пропускает завершающий '\n' — такое
# значение ушло бы в БД строкой-сиротой и в имя файла экспорта
MONTH_RE = re.compile(r'\d{4}-(0[1-9]|1[0-2])\Z')
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')


def _valid_month(month):
    return isinstance(month, str) and bool(MONTH_RE.fullmatch(month))


def _valid_date(date_str):
    """Корректная ISO-дата 'YYYY-MM-DD' (существующая)."""
    if not isinstance(date_str, str) or not DATE_RE.fullmatch(date_str):
        return False
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def _audit(action, summary, entity_date=None, employee_name=None):
    """Журнал графика, best-effort: сбой журнала не валит операцию."""
    try:
        u = current_user() or {}
        shifts_mgr.log_audit(
            action=action,
            summary=summary,
            actor_login=u.get('login'),
            actor_name=u.get('display_name') or u.get('login') or 'неизвестно',
            entity_date=entity_date,
            employee_name=employee_name,
        )
    except Exception as e:
        print(f"[SALARY AUDIT WARNING] журнал не записан ({action}): {e}")


@salary_bp.route('/api/salary/handover-penalty', methods=['POST'])
def set_handover_penalty():
    """Поставить/снять штраф за кассовую смену дня.

    Body: {date: 'YYYY-MM-DD', employee_name, penalized: bool, note?,
    employee_id?}. penalized=true — премия «передача смены» за этот день не
    платится (-500 ₽), false — штраф снят. Изменение пишется в журнал графика
    (handover_penalty); повторная простановка того же состояния — не событие.

    `employee_id` (стабильный ключ iiko, v10) — то, по чему штраф потом
    находится расчётом; `employee_name` остаётся снимком для журнала и показа.
    Поле опциональное: у сотрудника без id (нет в iiko) работает старый путь по
    имени.
    """
    data = request.get_json(silent=True) or {}
    date_str = data.get('date')
    if not _valid_date(date_str):
        return jsonify({'error': "date обязателен в формате YYYY-MM-DD"}), 400
    employee_name = data.get('employee_name')
    employee_name = employee_name.strip() if isinstance(employee_name, str) else ''
    if not employee_name:
        return jsonify({'error': 'employee_name обязателен'}), 400
    employee_id = data.get('employee_id')
    employee_id = employee_id.strip() if isinstance(employee_id, str) else None
    penalized = bool(data.get('penalized'))
    note = data.get('note')
    if note is not None and not isinstance(note, str):
        note = str(note)

    changed = shifts_mgr.set_handover_penalty(date_str, employee_name, penalized, note,
                                              employee_id=employee_id)

    if changed:
        d, m = date_str[8:10], date_str[5:7]
        if penalized:
            reason = f" ({note.strip()})" if note and note.strip() else ''
            summary = (f"Штраф кассы {d}.{m}: {employee_name} — премия за "
                       f"передачу смены за день снята{reason}")
        else:
            summary = f"Штраф кассы {d}.{m}: {employee_name} — штраф снят"
        _audit('handover_penalty', summary,
               entity_date=date_str, employee_name=employee_name)

    return jsonify({'ok': True, 'changed': changed})


@salary_bp.route('/api/salary/export', methods=['POST'])
def export_salary():
    """Экспорт таблицы ЗП за месяц в .xlsx (формат эталонной таблицы).

    Body — контракт build_salary_workbook (core/salary_export.py): фронт
    присылает уже посчитанные и смёрженные данные страницы, поэтому файл
    совпадает с показанным расчётом. Строки «Отпуск», «Доп доход», «мосты» и
    вычеты инвент/доп остаются пустыми — владелец заполняет их в Excel;
    выводимые строки (оплата, передача смены, такси, ИТОГО) — живые формулы,
    поэтому ручные правки пересчитываются в файле сами.
    """
    payload = request.get_json(silent=True) or {}
    month = payload.get('month') or ''
    if not _valid_month(month):
        return jsonify({'error': "month обязателен в формате YYYY-MM"}), 400
    if not payload.get('employees'):
        return jsonify({'error': 'Нет данных для экспорта — сначала выполните расчёт'}), 400

    try:
        wb = build_salary_workbook(payload)
    except Exception as e:
        print(f"[ERROR] Ошибка сборки экспорта ЗП: {e}")
        return jsonify({'error': f"Не удалось собрать файл: {e}"}), 500

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"salary_{month}.xlsx",
    )


@salary_bp.route('/api/salary/export-gsheet', methods=['POST'])
def export_salary_gsheet():
    """Экспорт таблицы ЗП за месяц в НОВУЮ Google Таблицу.

    Body — тот же контракт, что у /api/salary/export. Каждый вызов создаёт
    отдельную таблицу и возвращает ссылку; ничего существующего не трогает
    (в таблицу бухгалтерии данные уходят сами — ночная выгрузка 04:00,
    core/salary_scheduler.py).

    Ответы: 200 {url, tab} | 503 не настроено | 500.
    """
    payload = request.get_json(silent=True) or {}
    month = payload.get('month') or ''
    if not _valid_month(month):
        return jsonify({'error': "month обязателен в формате YYYY-MM"}), 400
    if not payload.get('employees'):
        return jsonify({'error': 'Нет данных для экспорта — сначала выполните расчёт'}), 400

    try:
        result = export_to_gsheet(payload)
    except GSheetNotConfigured as e:
        return jsonify({'error': str(e)}), 503
    except GSheetError as e:
        print(f"[ERROR] Экспорт ЗП в Google Таблицу: {e}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(f"[ERROR] Экспорт ЗП в Google Таблицу (непредвиденно): {e}")
        return jsonify({'error': f"Не удалось создать таблицу: {e}"}), 500

    _audit('salary_gsheet_export',
           f"Экспорт ЗП за {month} в новую Google Таблицу «{result['tab']}»")
    return jsonify(result)


@salary_bp.route('/api/salary/sync-gsheet', methods=['POST'])
def sync_salary_gsheet():
    """Прогнать ночную выгрузку в таблицу бухгалтерии прямо сейчас.

    Ручной запуск того же, что делает планировщик в 04:00
    (core/salary_scheduler.py): пишет вкладку «Июль_2026_Автоматическая» в
    SALARY_SHEET_ID. Нужен для проверки настройки и разовой досборки, чтобы
    не ждать ночи. Payload не принимает — собирает его на сервере сам.
    """
    from core.salary_scheduler import sync_once

    results = sync_once('manual')
    ok = {m: r for m, r in results.items() if isinstance(r, dict)}
    _audit('salary_gsheet_sync',
           'Ручной прогон выгрузки ЗП в таблицу бухгалтерии: '
           + (', '.join(f"{m} -> {r['tab']}" for m, r in ok.items()) or 'без результата'))
    return jsonify({'results': {m: (r if isinstance(r, dict) else str(r))
                                for m, r in results.items()}})

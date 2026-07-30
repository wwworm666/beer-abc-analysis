"""
API страницы расчёта ЗП (/salary): ручные корректировки и экспорт в Excel.

Корректировки (отпуск, доп доход, вычеты) хранятся в shifts.db
(salary_adjustments, схема v8) по ключу месяц + имя сотрудника + категория —
страница мёржит источники по имени, поэтому и корректировки ключуются именем.
Каждое изменение суммы пишется в журнал графика (schedule_audit) — как ставки
ролей: кто и когда вписал вычет, видно в истории.

Экспорт принимает уже посчитанные страницей данные (payload — контракт в
core/salary_export.py) и отдаёт .xlsx в формате эталонной таблицы владельца:
экспорт бит-в-бит совпадает с тем, что показывает страница.
"""

import io
import math
import re
from flask import Blueprint, request, jsonify, send_file

from extensions import shifts_mgr
from core.auth_guard import current_user
from core.shifts_manager import SALARY_ADJUSTMENT_CATEGORIES
from core.salary_export import build_salary_workbook

salary_bp = Blueprint('salary', __name__)

# fullmatch + \Z-семантика: '$' в re пропускает завершающий '\n' — такой month
# ушёл бы в БД строкой-сиротой и в имя файла экспорта
MONTH_RE = re.compile(r'\d{4}-(0[1-9]|1[0-2])\Z')


def _valid_month(month):
    return isinstance(month, str) and bool(MONTH_RE.fullmatch(month))

# Потолок одной корректировки — против опечаток (как CASH_MAX_RUB у кассы).
ADJUSTMENT_MAX_RUB = 1_000_000


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


def _fmt_amount(v):
    """Сумма для строки журнала: целые без копеек."""
    if v is None:
        return '—'
    v = float(v)
    return f"{v:.0f}" if v == int(v) else f"{v:.2f}"


@salary_bp.route('/api/salary/adjustments', methods=['GET'])
def get_adjustments():
    """Корректировки за месяц. Query: month='YYYY-MM'.

    Ответ: {month, categories, adjustments: {имя: {категория: {amount, note}}}}.
    categories — словарь код->русская подпись (единый источник для фронта).
    """
    month = request.args.get('month') or ''
    if not _valid_month(month):
        return jsonify({'error': "month обязателен в формате YYYY-MM"}), 400
    return jsonify({
        'month': month,
        'categories': SALARY_ADJUSTMENT_CATEGORIES,
        'adjustments': shifts_mgr.get_salary_adjustments(month),
    })


@salary_bp.route('/api/salary/adjustments', methods=['POST'])
def set_adjustment():
    """Записать одну корректировку (UPSERT; сумма 0 без заметки = удалить).

    Body: {month, employee_name, category, amount, note?}. Суммы в рублях,
    неотрицательные (знак задаёт категория: deduction_* вычитаются из ЗП).
    Изменение суммы пишется в журнал графика (salary_adjustment).
    """
    data = request.get_json(silent=True) or {}
    month = data.get('month') or ''
    if not _valid_month(month):
        return jsonify({'error': "month обязателен в формате YYYY-MM"}), 400
    employee_name = data.get('employee_name')
    employee_name = employee_name.strip() if isinstance(employee_name, str) else ''
    if not employee_name:
        return jsonify({'error': 'employee_name обязателен'}), 400
    category = data.get('category')
    if category not in SALARY_ADJUSTMENT_CATEGORIES:
        allowed = ', '.join(SALARY_ADJUSTMENT_CATEGORIES)
        return jsonify({'error': f"category должна быть одной из: {allowed}"}), 400
    try:
        amount = float(data.get('amount') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'amount должен быть числом'}), 400
    # isfinite отсекает NaN/inf: NaN проходит сравнения ниже (все False) и
    # ломал бы и запись, и строку журнала
    if not math.isfinite(amount) or amount < 0 or amount > ADJUSTMENT_MAX_RUB:
        return jsonify({'error': f"amount должен быть в пределах 0..{ADJUSTMENT_MAX_RUB}"}), 400
    note = data.get('note')
    if note is not None and not isinstance(note, str):
        note = str(note)  # число в note — не повод для 500

    old_amount = shifts_mgr.set_salary_adjustment(
        month, employee_name, category, amount, note)

    if (old_amount or 0) != amount:
        label = SALARY_ADJUSTMENT_CATEGORIES[category]
        _audit('salary_adjustment',
               f"ЗП {month}: «{label}» {employee_name}: "
               f"{_fmt_amount(old_amount)} -> {_fmt_amount(amount)} ₽",
               entity_date=f"{month}-01", employee_name=employee_name)

    return jsonify({'ok': True, 'old_amount': old_amount})


@salary_bp.route('/api/salary/export', methods=['POST'])
def export_salary():
    """Экспорт таблицы ЗП за месяц в .xlsx (формат эталонной таблицы).

    Body — контракт build_salary_workbook (core/salary_export.py): фронт
    присылает уже посчитанные и смёрженные данные страницы, поэтому файл
    совпадает с показанным расчётом. Корректировки в payload тоже с фронта —
    те же значения, что были на экране в момент экспорта.
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

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
from datetime import date, datetime
from flask import Blueprint, request, jsonify, send_file

from extensions import shifts_mgr
from core.auth_guard import current_user, admin_required
from core.shifts_manager import HandoverPenaltyConflict
from core.salary_export import build_salary_workbook
from core.salary_gsheet import GSheetError, GSheetNotConfigured, export_to_gsheet
from core.cash_register import (
    CASH_MAX_RUB, PROBLEM_LABELS, build_register, fmt_kop, rub_to_kop)

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


def _is_full_month(date_from, date_to, month):
    """Совпадает ли период расчёта с целым календарным месяцем `month`.

    Возвращает (ok, причина_отказа). Нужна Google-выгрузке: она переписывает
    вкладку месяца целиком, а период на странице ЗП — свободный диапазон.
    Старая открытая страница дат не присылает — тоже отказ, иначе она молча
    затёрла бы вкладку данными неизвестного периода.
    """
    from core.salary_payload import month_bounds

    if not (_valid_date(date_from) and _valid_date(date_to)):
        return False, ('Обновите страницу и повторите расчёт: выгрузка в Google '
                       'требует период расчёта, а он не передан')
    want_from, want_to = month_bounds(month)
    if (date_from, date_to) != (want_from, want_to):
        return False, (f"Выгрузка в Google — только за целый месяц. Выбран период "
                       f"{date_from}..{date_to}, нужен {want_from}..{want_to}: "
                       f"вкладка «{month}» в таблице бухгалтерии переписывается "
                       f"целиком, и половина месяца затёрла бы весь месяц")
    return True, ''


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

    try:
        changed = shifts_mgr.set_handover_penalty(date_str, employee_name, penalized,
                                                  note, employee_id=employee_id)
    except HandoverPenaltyConflict as e:
        # Два сотрудника с одинаковым ФИО на одном дне — записи неразличимы.
        # Отказываем явно, вместо того чтобы перевесить чужой штраф.
        return jsonify({'error': str(e)}), 409

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


# ==================== Кассовый регистр (раздел «Касса за месяц») ====================
# Рабочий стол бухгалтера: все смены периода с кассой и ПРОБЕЛАМИ (дни, за которые
# кассу не сдали). Сборка строк — core/cash_register.py (чистая функция, тесты
# tests/test_cash_register.py); здесь только чтение БД, права и журнал.
#
# Права: смотреть — всем (как любую бизнес-страницу), править — только
# администратору. Правка из регистра идёт БЕЗ окна 72 ч, которым заперта касса на
# странице графика (routes/schedule.py: CASH_EDIT_WINDOW_HOURS) — в этом и смысл
# раздела: внести то, что бармен забыл, всплывшее в чате через неделю. Окно на
# графике остаётся: оно защищает кассовую дисциплину от правок задним числом
# СВОИХ смен, а здесь правит владелец, и каждое изменение попадает в журнал.

# Потолок диапазона регистра. Период на странице ЗП — свободный, но регистр за
# годы разом никому не нужен, а вот память и трафик он съест.
CASH_REGISTER_MAX_DAYS = 366


def _handover_rule():
    """(дата-отсечка правила «нет кассы — нет премии», тариф премии).

    Импорт внутри функции: константы живут в routes/employee.py (там считается
    премия), и импорт на уровне модуля связал бы два блюпринта при загрузке.
    """
    from routes.employee import HANDOVER_CASH_RULE_FROM, HANDOVER_RATE
    return HANDOVER_CASH_RULE_FROM, HANDOVER_RATE


def _period_from_request():
    """(date_from, date_to, ошибка) из query-параметров запроса."""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    if not (_valid_date(date_from) and _valid_date(date_to)):
        return None, None, 'date_from и date_to обязательны в формате YYYY-MM-DD'
    if date_from > date_to:
        return None, None, 'date_from позже date_to'
    days = (datetime.strptime(date_to, '%Y-%m-%d')
            - datetime.strptime(date_from, '%Y-%m-%d')).days + 1
    if days > CASH_REGISTER_MAX_DAYS:
        return None, None, (f'Слишком длинный период: {days} дн., максимум '
                            f'{CASH_REGISTER_MAX_DAYS}')
    return date_from, date_to, None


@salary_bp.route('/api/salary/cash-register', methods=['GET'])
def cash_register():
    """Кассовый регистр за период: строки по сменам, пробелы, штрафы, итоги.

    Query: date_from, date_to (включительно). Возвращает всё, что нужно разделу
    «Касса за месяц» на странице ЗП: строки (сборка — build_register), список
    точек периода для фильтра, итоги, подписи проблем, право на правку.
    Фильтрация/поиск — на фронте: данные месяца это ~140 строк, гонять запрос на
    каждый щелчок фильтра незачем.
    """
    date_from, date_to, err = _period_from_request()
    if err:
        return jsonify({'error': err}), 400

    rule_from, rate = _handover_rule()
    reg = build_register(
        shifts_mgr.get_shifts_for_period(date_from, date_to),
        shifts_mgr.get_handover_penalties(date_from, date_to),
        today=date.today().isoformat(),
        rule_from=rule_from,
    )
    from routes.schedule import CASH_EDIT_WINDOW_HOURS
    reg.update({
        'date_from': date_from,
        'date_to': date_to,
        'rule_from': rule_from,
        'handover_rate': rate,
        'cash_max_rub': CASH_MAX_RUB,
        'edit_window_hours': CASH_EDIT_WINDOW_HOURS,
        'problem_labels': PROBLEM_LABELS,
        'can_edit': bool((current_user() or {}).get('is_admin')),
    })
    return jsonify(reg)


def _cash_diff_summary(sh, exp, col, end, note):
    """Человекочитаемый список изменений кассы для журнала (только изменённое).

    Задним числом правят редко и точечно — в истории должно быть видно, что
    именно стало другим, а не «касса переписана».
    """
    parts = []
    for label, old, new in (('траты', sh.get('cash_expense_kop'), exp),
                            ('инкассация', sh.get('cash_collection_kop'), col),
                            ('на конец', sh.get('cash_end_kop'), end)):
        if old != new:
            parts.append(f"{label} {fmt_kop(old)} -> {fmt_kop(new)}")
    old_note = (sh.get('cash_expense_note') or '').strip() or None
    if old_note != note:
        parts.append(f"«на что» «{old_note or '—'}» -> «{note or '—'}»")
    return parts


@salary_bp.route('/api/salary/cash-register/shift/<int:shift_id>', methods=['PUT'])
@admin_required
def cash_register_set(shift_id):
    """Внести/исправить кассу смены из регистра — без окна правок (только админ).

    Body в РУБЛЯХ (число, строка или null): {cash_expense, cash_collection,
    cash_end, cash_expense_note}. Все три суммы null = очистить кассу смены.
    Плюс штраф за передачу смены тем же запросом:
      penalize = true  -> проставить штраф на (дата, сотрудник смены);
      penalize = false -> снять;
      поле отсутствует -> штраф не трогаем.
    penalty_note — причина (текст в журнал и в подсказку регистра).

    Зачем штраф здесь: без него внесение кассы задним числом ВОЗВРАЩАЕТ бармену
    премию 500 ₽ за день, который он не закрыл — автоправило видит заполненную
    кассу и платит. Поэтому регистр предлагает штраф в той же форме, где вносят
    сумму, и премия остаётся снятой (решение владельца 2026-08-07).

    Ответ: {ok, cash_changed, penalty_changed, penalized, premium_restored_for}.
    `premium_restored_for` — сотрудники ДРУГИХ смен этой точки за этот день, к
    которым премия вернулась (их штраф не касается): у вечернего бармена касса
    не его обязанность, но раньше он терял премию вместе с дневным.
    """
    data = request.get_json(silent=True) or {}
    ok_e, exp = rub_to_kop(data.get('cash_expense'))
    ok_c, col = rub_to_kop(data.get('cash_collection'))
    ok_k, end = rub_to_kop(data.get('cash_end'))
    if not (ok_e and ok_c and ok_k):
        return jsonify({'error': f'Суммы кассы — число от 0 до {CASH_MAX_RUB} ₽'}), 400
    note = data.get('cash_expense_note')
    if note is not None and not isinstance(note, str):
        return jsonify({'error': 'cash_expense_note должен быть строкой'}), 400
    note = (note or '').strip() or None

    sh = shifts_mgr.get_shift(shift_id)
    if not sh:
        return jsonify({'error': 'Смена не найдена'}), 404

    # Кому премия вернётся: день точки был БЕЗ кассы, а теперь закрывается.
    restored = []
    if end is not None and sh.get('cash_end_kop') is None:
        same_day = shifts_mgr.get_shifts_for_period(sh['date'], sh['date'])
        day_closed = any(o.get('cash_end_kop') is not None for o in same_day
                         if o.get('location_id') == sh.get('location_id'))
        if not day_closed:
            restored = sorted({o.get('employee_name') for o in same_day
                               if o.get('location_id') == sh.get('location_id')
                               and o.get('id') != shift_id
                               and (o.get('employee_name') or '').strip()})

    dm = f"{sh['date'][8:10]}.{sh['date'][5:7]}"
    changes = _cash_diff_summary(sh, exp, col, end, note)
    cash_changed = bool(changes)
    if cash_changed:
        if not shifts_mgr.set_shift_cash(shift_id, exp, col, end, note):
            return jsonify({'error': 'Смена не найдена'}), 404
        _audit('cash_admin_set',
               f"Касса задним числом ({sh['employee_name']}, {dm}, "
               f"{sh.get('location_short') or ''}): " + '; '.join(changes),
               entity_date=sh['date'], employee_name=sh['employee_name'])

    penalty_changed = False
    penalized = None
    if 'penalize' in data:
        penalized = bool(data.get('penalize'))
        pnote = data.get('penalty_note')
        pnote = pnote.strip() if isinstance(pnote, str) else None
        try:
            penalty_changed = shifts_mgr.set_handover_penalty(
                sh['date'], sh['employee_name'], penalized, pnote or None,
                employee_id=(sh.get('employee_id') or None))
        except HandoverPenaltyConflict as e:
            # Касса уже записана — сообщаем именно про штраф, чтобы владелец не
            # думал, что не сохранилось ничего.
            return jsonify({'error': f"Касса сохранена, штраф — нет: {e}"}), 409
        if penalty_changed:
            reason = f" ({pnote})" if pnote else ''
            _audit('handover_penalty',
                   (f"Штраф кассы {dm}: {sh['employee_name']} — премия за "
                    f"передачу смены за день снята{reason}") if penalized
                   else f"Штраф кассы {dm}: {sh['employee_name']} — штраф снят",
                   entity_date=sh['date'], employee_name=sh['employee_name'])

    return jsonify({'ok': True, 'cash_changed': cash_changed,
                    'penalty_changed': penalty_changed, 'penalized': penalized,
                    'premium_restored_for': restored})


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
    """Обновить Google Таблицу бухгалтерии расчётом за месяц — прямо сейчас.

    Body — тот же контракт, что у /api/salary/export. Пишет ту же вкладку
    «Июль_2026_Автоматическая» таблицы SALARY_SHEET_ID, что и ночная выгрузка
    в 04:00 (core/salary_scheduler.py), но за месяц, открытый на странице.
    Ручная вкладка бухгалтера («июль2026») не трогается.

    Раньше эндпоинт создавал НОВУЮ таблицу и падал 403: сервис-аккаунту
    недоступно создание файлов. Этот путь остался фоллбэком, если
    SALARY_SHEET_ID не задан.

    Ответы: 200 {url, tab} | 503 не настроено | 500.
    """
    payload = request.get_json(silent=True) or {}
    month = payload.get('month') or ''
    if not _valid_month(month):
        return jsonify({'error': "month обязателен в формате YYYY-MM"}), 400
    if not payload.get('employees'):
        return jsonify({'error': 'Нет данных для экспорта — сначала выполните расчёт'}), 400

    # Вкладка месяца в таблице бухгалтерии переписывается ЦЕЛИКОМ, поэтому
    # выгружать можно только расчёт за полный месяц. Период на странице —
    # свободный диапазон (flatpickr range), и без этой проверки расчёт за
    # 01.07–15.07 затёр бы июль половинными часами и премиями, а ночная
    # выгрузка после 7 числа предыдущий месяц уже не обновляет — то есть само
    # бы не починилось. Файл .xlsx этой проверки не требует: он ничего не
    # перезаписывает.
    ok, why = _is_full_month(payload.get('date_from'), payload.get('date_to'), month)
    if not ok:
        return jsonify({'error': why}), 400

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
           f"Обновление Google Таблицы ЗП за {month}, вкладка «{result['tab']}»")
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

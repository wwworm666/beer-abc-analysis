"""
Резолвер личности для личного кабинета `/me`: аккаунт -> сотрудник -> строка снимка.

## Что это

Единственное место, которое решает, ЧЬИ данные показать человеку на `/me`.
Функции чистые: ни Flask, ни сети, ни БД — всё приходит аргументами, поэтому
модуль тестируется целиком без моков (`tests/test_me_identity.py`).

## Железное правило

Показать бармену чужую зарплату — ошибка, которую нельзя допустить. Поэтому:
**лучше явное «не смогли сопоставить», чем чужая или недостоверная цифра.**
Любой отказ — это статус с русским текстом и указанием, кто чинит, а НЕ нули:
молчаливый ноль в блоке денег читается как «мне не начислили», то есть
дезинформирует. Ровно этим плох путь `/schedule/cal.ics` (routes/schedule.py):
при отсутствии привязки он отдаёт 200 и пустой календарь.

## Идентичность — только стабильный id

Единственный якорь — `users.employee_iiko_id` (привязка, которую ставит админ в
`/admin/users`). Он напрямую сравним с `shifts.employee_id`, с `employee_id` в
строках расчёта премий и KPI и с ключом снимка: это один и тот же GUID из iiko
(`responsibleUserId` кассовых смен). Ни один шаг резолвера не идёт по
`display_name` аккаунта — от неявной связи по имени проект осознанно ушёл
(см. docs/auth.md), и возврат к ней означал бы чужую зарплату.

## Почему свой матчер имён, а не общий

`core/salary_payload.py::_names_match` считает совпадением подмножество из
ОДНОГО слова: {'юреня'} <= {'юреня', 'иван'} -> True. Для мёржа расчёта это
осознанный компромисс, но для «показать человеку его деньги» — источник ошибки
у однофамильцев. Здесь правило строже (`strict_same_name`): множества слов
должны быть РАВНЫ и слов должно быть минимум два. Все остальные матчеры проекта
тоже требуют >= 2 слов — исключение только в мёрже ЗП.

## Файлы

- `core/me_identity.py` — этот модуль (резолвер, статусы, правило имён).
- `core/me_snapshot.py` — импортирует отсюда `SNAPSHOT_SCHEMA`, `strict_same_name`
  и `norm_name`, чтобы правило имён и версия формата были в одном месте.
- `routes/me.py` — вызывает `resolve_me` и отдаёт результат в `/api/me`.
- `tests/test_me_identity.py` — тесты.

## Changelog

- 2026-08-13 — модуль создан вместе со страницей `/me`.
"""

from typing import Dict, List, Optional

# Версия формата снимка. Общий контракт писателя (`core/me_snapshot.py`) и
# читателя (этот модуль): если файл на диске построен другой версией, деньги и
# KPI не показываются вовсе — откат деплоя не должен приводить к чтению «не
# своего» файла. Живёт здесь, а не в снимке, чтобы не было кольцевого импорта.
SNAPSHOT_SCHEMA = 1

# --- статусы резолва ---
OK = 'ok'
NOT_LINKED = 'not_linked'
UNKNOWN_EMPLOYEE = 'unknown_employee'
AMBIGUOUS_LINK = 'ambiguous_link'
NO_SNAPSHOT = 'no_snapshot'
SCHEMA_MISMATCH = 'schema_mismatch'
NOT_IN_SNAPSHOT = 'not_in_snapshot'

# Статусы, при которых деньги/KPI/показатели не отдаются вообще.
REFUSING_STATUSES = (NOT_LINKED, UNKNOWN_EMPLOYEE, AMBIGUOUS_LINK,
                     NO_SNAPSHOT, SCHEMA_MISMATCH, NOT_IN_SNAPSHOT)


# ==================== правило имён ====================

def norm_name(name: str) -> str:
    """Имя в нормальной форме: слова по алфавиту, нижний регистр.

    «Васильев Никита» и «Никита Васильев» дают одну строку. Зеркалит
    `ShiftsManager._norm_name` (core/shifts_manager.py) — то же правило, что
    использует синхронизация реестра сотрудников.
    """
    return ' '.join(sorted((name or '').strip().lower().split()))


def name_words(name: str) -> set:
    return set((name or '').strip().lower().split())


def strict_same_name(a: str, b: str) -> bool:
    """Строгое совпадение имён: множества слов РАВНЫ и слов минимум два.

    Порядок слов не важен («Юреня Роман» == «Роман Юреня»), но подмножество
    совпадением НЕ считается: strict_same_name('Юреня', 'Юреня Иван') is False.
    Именно этим правило отличается от `_names_match` в core/salary_payload.py,
    где хватает одного общего слова — а одного слова достаточно, чтобы часы
    одного бармена уехали к его однофамильцу.

    Одно слово не связывает никогда: фамилии повторяются, и «Юреня» может быть
    и Романом, и Иваном.
    """
    wa, wb = name_words(a), name_words(b)
    if len(wa) < 2 or len(wb) < 2:
        return False
    return wa == wb


def is_name_unique(name: str, names: List[str]) -> bool:
    """Единственное ли это имя в списке (сравнение нормализованное).

    Нужно, чтобы не утверждать принадлежность часов человеку, у которого в
    реестре есть полный тёзка: проект уже признаёт такие случаи неразрешимыми
    (HandoverPenaltyConflict в core/shifts_manager.py) и отвечает отказом, а не
    догадкой.
    """
    target = norm_name(name)
    if not target:
        return False
    return sum(1 for n in names if norm_name(n) == target) <= 1


# ==================== тексты отказов ====================

MSG = {
    NOT_LINKED: (
        'Ваш аккаунт не привязан к сотруднику графика. Личная страница '
        'заполнится, когда администратор свяжет ваш логин с именем из iiko: '
        'страница «Аккаунты» -> ваш логин -> столбец «Сотрудник».'
    ),
    UNKNOWN_EMPLOYEE: (
        'Привязка аккаунта указывает на сотрудника, которого нет ни в графике, '
        'ни в расчёте: {emp_id}. Похоже, привязка сделана с ошибкой — покажите '
        'это администратору.'
    ),
    AMBIGUOUS_LINK: (
        'К этому сотруднику привязано несколько аккаунтов: {logins}. Пока '
        'привязка не исправлена, показатели и деньги не показываются — иначе '
        'кто-то из вас увидел бы чужие. Исправляется на странице «Аккаунты».'
    ),
    NO_SNAPSHOT: (
        'Снимок за {month} ещё не собран. Смены и часы ниже — живые, они '
        'работают всегда. Показатели, KPI и деньги появятся после первого '
        'расчёта: он идёт каждую ночь, либо запустите кнопкой «Обновить».'
    ),
    SCHEMA_MISMATCH: (
        'Снимок за {month} построен другой версией приложения, поэтому '
        'показатели и деньги из него не читаются. Нужен пересчёт — кнопка '
        '«Обновить».'
    ),
    NOT_IN_SNAPSHOT: (
        'В расчёте за {month} вас нет: за этот месяц в iiko нет закрытых '
        'кассовых смен на ваше имя, а в графике нет смен, привязанных к вашему '
        'идентификатору. Если смены были — попросите администратора запустить '
        'синхронизацию сотрудников на странице графика.'
    ),
}

ISSUE_MSG = {
    'hours_matched_by_name': (
        'Часы за {month} подставлены по совпадению имени, а не по вашему '
        'идентификатору. Суммы верны, если это действительно ваши смены — '
        'проверьте по календарю.'
    ),
    'hours_attribution_unsafe': (
        'Часы за {month} не удалось надёжно связать с вашим идентификатором, '
        'поэтому оплата часов и такси в итог НЕ включены. Это не значит, что их '
        'не начислят — это значит, что приложение не готово поручиться за цифру. '
        'Администратору: запустить «Синхронизировать сотрудников» на странице '
        'графика.'
    ),
    'hours_unlinked_shifts': (
        'За {month} есть {hours} ч ({pay} руб.) на имя «{name}» без привязки к '
        'вашему идентификатору. В итог они не включены — так же, как в расчёте '
        'зарплаты. Чинится синхронизацией реестра сотрудников.'
    ),
    'hours_unlinked_shifts_maybe': (
        'За {month} есть {hours} ч ({pay} руб.) на имя «{name}» без привязки к '
        'идентификатору. В графике есть полный тёзка, поэтому утверждать, что '
        'это ваши часы, нельзя. В итог они не включены. Разбирается '
        'администратором через синхронизацию реестра сотрудников.'
    ),
    'metrics_unavailable': (
        'Показатели продаж за {month} не посчитаны: не удалось однозначно '
        'сопоставить ваше имя с именем в отчётах продаж iiko. Нули здесь были бы '
        'обманом, поэтому показатели скрыты. Администратору: проверить написание '
        'имени в iiko.'
    ),
    'kpi_unavailable': (
        'KPI за {month} не рассчитан: {reason}'
    ),
}

KPI_NO_DATA_REASON = ('на месяц не заданы KPI-цели либо нет закрытых смен. '
                      'Цели настраиваются на странице «Цели месяца».')


# ==================== резолвер ====================

def _issue(code: str, severity: str, message: str, detail: Dict = None) -> Dict:
    return {'code': code, 'severity': severity, 'message': message,
            'detail': detail or {}}


def _result(status: str, *, employee_id=None, employee_name=None,
            row=None, issues=None, message='') -> Dict:
    return {
        'status': status,
        'employee_id': employee_id,
        'employee_name': employee_name,
        'row': row,
        'message': message,
        'issues': issues or [],
    }


def find_in_registry(registry: List[Dict], iiko_id: str) -> Optional[Dict]:
    """Сотрудник реестра графика по стабильному id (строгое равенство строк).

    Готового метода в ShiftsManager нет — точечный поиск в проекте делают так же
    вручную (routes/schedule.py). Сравнение через str(): в реестр id приходит из
    SQLite, в аккаунт — из формы, и оба должны сойтись как строки.
    """
    if not iiko_id:
        return None
    target = str(iiko_id).strip()
    for e in registry or []:
        if e.get('id') and str(e['id']).strip() == target:
            return e
    return None


def resolve_me(user: Dict, snapshot: Dict, *, month: str = '',
               registry: List[Dict] = None, linked_users: List[Dict] = None,
               expected_schema: int = SNAPSHOT_SCHEMA) -> Dict:
    """Кто это и какую строку снимка ему показывать.

    Аргументы:
      user         — `current_user()` (core/auth_guard.py), перечитывается из БД
                     на каждом запросе, поэтому привязка всегда свежая;
      snapshot     — прочитанный файл месяца или {} (файла нет — штатно);
      month        — 'YYYY-MM', только для текстов;
      registry     — `shifts_mgr.get_schedule_employees(include_inactive=True)`;
      linked_users — `auth_mgr.list_users_by_employee_id(id)`.

    Возвращает словарь с `status`, `employee_id`, `employee_name`, `row`
    (строка снимка; None при любом отказе), `message` и `issues`.
    Исключений не бросает: отсутствие данных — это статус, а не ошибка.
    """
    registry = registry or []
    linked_users = linked_users or []
    snapshot = snapshot or {}

    raw_id = (user or {}).get('employee_iiko_id')
    iiko_id = str(raw_id).strip() if raw_id not in (None, '') else ''
    if not iiko_id:
        return _result(NOT_LINKED, message=MSG[NOT_LINKED])

    # Два аккаунта на одного сотрудника: создать такое больше нельзя
    # (AuthManager.set_employee_link), но дубль мог остаться с прежних времён.
    # Отказываем ДО всякого чтения снимка — иначе оба аккаунта увидели бы одну
    # и ту же зарплату, и как минимум один из них — чужую.
    active_logins = sorted({u.get('login') for u in linked_users
                            if u.get('active') and u.get('login')})
    if len(active_logins) > 1:
        return _result(AMBIGUOUS_LINK, employee_id=iiko_id,
                       message=MSG[AMBIGUOUS_LINK].format(logins=', '.join(active_logins)))

    reg_emp = find_in_registry(registry, iiko_id)
    snap_row = (snapshot.get('employees') or {}).get(iiko_id)

    # Привязка на id, которого нет нигде. Проверяем только если реестр вообще
    # прочитался: пустой реестр означает недоступность shifts.db, а не то, что
    # сотрудника не существует.
    if registry and reg_emp is None and snap_row is None:
        return _result(UNKNOWN_EMPLOYEE, employee_id=iiko_id,
                       message=MSG[UNKNOWN_EMPLOYEE].format(emp_id=iiko_id))

    name = ((reg_emp or {}).get('name')
            or (snap_row or {}).get('name_schedule')
            or (snap_row or {}).get('name_iiko')
            or (user or {}).get('display_name') or '')

    if not snapshot:
        return _result(NO_SNAPSHOT, employee_id=iiko_id, employee_name=name,
                       message=MSG[NO_SNAPSHOT].format(month=month or 'этот месяц'))
    if snapshot.get('_schema') != expected_schema:
        return _result(SCHEMA_MISMATCH, employee_id=iiko_id, employee_name=name,
                       message=MSG[SCHEMA_MISMATCH].format(month=month or 'этот месяц'))
    if snap_row is None:
        return _result(NOT_IN_SNAPSHOT, employee_id=iiko_id, employee_name=name,
                       message=MSG[NOT_IN_SNAPSHOT].format(month=month or 'этот месяц'))

    issues = collect_issues(snap_row, snapshot, name=name, month=month,
                            registry=registry)
    return _result(OK, employee_id=iiko_id, employee_name=name,
                   row=snap_row, issues=issues)


def collect_issues(row: Dict, snapshot: Dict, *, name: str, month: str,
                   registry: List[Dict] = None) -> List[Dict]:
    """Предупреждения к найденной строке: что в цифрах может быть не так.

    Вердикт по часам (`hours.trust`) считается при сборке снимка
    (core/me_snapshot.py) — здесь он только переводится в человеческий текст,
    чтобы правило доверия жило в одном месте.
    """
    registry = registry or []
    month_label = month or 'этот месяц'
    issues = []

    hours = row.get('hours') or {}
    trust = hours.get('trust')
    if trust == 'name_strict':
        issues.append(_issue('hours_matched_by_name', 'warn',
                             ISSUE_MSG['hours_matched_by_name'].format(month=month_label),
                             {'employee_name': hours.get('employee_name')}))
    elif trust == 'unsafe':
        excluded = (row.get('money') or {}).get('excluded_components') or []
        issues.append(_issue('hours_attribution_unsafe', 'error',
                             ISSUE_MSG['hours_attribution_unsafe'].format(month=month_label),
                             {'excluded_components': excluded}))

    # Осиротевшие часы: строка графика с тем же полным именем, но без
    # employee_id. Причина — GROUP BY COALESCE(employee_id, employee_name) в
    # ShiftsManager.get_hours_by_role_for_period: человек, у которого часть смен
    # без id, распадается на две строки. Не складываем их: страница /salary, по
    # которой платят, тоже не складывает, и показать сумму больше выплаты хуже,
    # чем назвать недостающую часть с причиной.
    registry_names = [e.get('name') for e in registry if e.get('name')]
    unique = is_name_unique(name, registry_names)
    for orphan in snapshot.get('unlinked_hours') or []:
        if not strict_same_name(orphan.get('employee_name'), name):
            continue
        code = 'hours_unlinked_shifts' if unique else 'hours_unlinked_shifts_maybe'
        issues.append(_issue(
            'hours_unlinked_shifts', 'warn',
            ISSUE_MSG[code].format(
                month=month_label,
                hours=_fmt_num(orphan.get('total_hours')),
                pay=_fmt_num(orphan.get('total_pay')),
                name=orphan.get('employee_name') or name),
            {'hours': orphan.get('total_hours'), 'pay': orphan.get('total_pay'),
             'day_shifts': orphan.get('day_shifts'), 'certain': unique}))

    metrics = row.get('metrics') or {}
    if metrics.get('status') and metrics['status'] != 'ok':
        issues.append(_issue('metrics_unavailable', 'warn',
                             ISSUE_MSG['metrics_unavailable'].format(month=month_label),
                             {'reason': metrics['status']}))

    kpi = row.get('kpi') or {}
    if kpi.get('status') and kpi['status'] != 'ok':
        issues.append(_issue('kpi_unavailable', 'warn',
                             ISSUE_MSG['kpi_unavailable'].format(
                                 month=month_label, reason=KPI_NO_DATA_REASON),
                             {'reason': kpi['status']}))

    return issues


def _fmt_num(value) -> str:
    """Число для текста сообщения: 16.0 -> «16», 16.5 -> «16,5».

    Форматирование здесь, а не на фронте, потому что текст issue собирается
    целиком на сервере — иначе одна и та же формулировка разъехалась бы между
    страницей и журналом.
    """
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return '0'
    if abs(num - round(num)) < 0.05:
        return f'{int(round(num))}'
    return f'{num:.1f}'.replace('.', ',')

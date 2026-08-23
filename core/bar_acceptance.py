"""
Приёмка бара на открытии смены — «Как принял бар?».

## Что это

Один вопрос, который бармен видит на `/me` в день своей открывающей смены:

| Ответ | Что требуется | Смысл |
|-------|---------------|-------|
| Чисто | ничего | бар принят в порядке |
| Замечания | одна строка «что не так» | мелочи, которые надо знать, но смена работает |
| Плохо | строка + фото | так оставлять бар нельзя, есть доказательство |

Это первый шаг цифровизации правил чистоты: раньше «бар оставили грязным»
существовало только в устном пересказе и всплывало через неделю без даты, без
имени и без фотографии. Теперь у каждого дня точки есть отметка, автор и время.

Модуль — ЧИСТАЯ сборка правил: на входе смены и уже прочитанные приёмки, на
выходе строки журнала и результат валидации. Ни БД, ни Flask, ни файловой
системы — поэтому проверяется тестами целиком (`tests/test_bar_acceptance.py`).

## Кто отвечает

Только ОТКРЫВАЮЩАЯ смена точки за день — первая дневная по времени старта
(`core/cash_register.opening_shifts`, там же это правило выбирает ответственного
за кассу). Причина одна и та же: принимает бар тот, кто пришёл на закрытый бар
после ночи. Вечерний второй бармен выходит на работающий бар — ему нечего
принимать, и его ответ был бы про смену коллеги, а не про закрытие.

Отсюда: ровно одна приёмка на (точку, день). Второй дневной бармен той же точки
вопроса не видит.

## Проблемы строки (`problems`)

- `not_marked` — «не отмечено»: день прошёл, правило уже действовало, у
  открывающей смены нет ответа. Это тот же вид сигнала, что `no_cash` в кассовом
  регистре: пробел важнее любого ответа, потому что пробел — это день, про
  который не известно ничего.

Чего в проблемах СОЗНАТЕЛЬНО нет: самого ответа «Плохо». «Плохо» — не проблема
журнала, а его нормальная работа: бармен сказал правду, и система сработала.
Пометить его проблемой значило бы наказывать за честность — и через месяц все
ответы стали бы «Чисто».

## Дата отсечки

`RULE_FROM` — день, с которого вопрос вообще задаётся. До него пробелов нет:
тогда этого вопроса не существовало, и покрасить всю историю в «не отмечено»
означало бы утопить настоящие пробелы в шуме. Ровно так же устроено
`HANDOVER_CASH_RULE_FROM` в правиле «нет кассы — нет премии».

## Окно ответа

Ответить можно ТОЛЬКО в день смены (по Москве). Приёмка описывает момент — «как
я принял бар утром»; ответ, данный через три дня, это уже не наблюдение, а
воспоминание, и возможность переписать его задним числом обнулила бы смысл
доказательства. Забыли — день остаётся `not_marked`, и это честнее, чем
проставленное задним числом «Чисто».

Внутри дня ответ можно поправить (опечатка, «сначала не заметил»): строка
перезаписывается, `created_at` остаётся от первого ответа, поэтому журнал
отличает исправленный ответ от первичного.

## Файлы

- `core/bar_acceptance.py` — этот модуль (правила, валидация, сборка журнала).
- `core/bar_photo_store.py` — хранение фото на диске.
- `core/shifts_manager.py` — таблица `bar_acceptance` (схема v11), чтение/запись.
- `core/cash_register.py` — `opening_shifts()`: кто открывающий (общее правило).
- `routes/cleanliness.py` — страница `/cleanliness` и API.
- `static/js/me/acceptance.js` — карточка вопроса на `/me`.
- `tests/test_bar_acceptance.py` — тесты.

Подробнее — `docs/cleanliness.md`.

## Changelog

- 2026-08-23 — модуль создан.
"""

from typing import Dict, List, Optional, Tuple

from core.cash_register import opening_shifts

# Ответы. Значения уходят на фронт и в БД как есть; подписи — в STATUS_LABELS,
# чтобы формулировка была одна и в карточке бармена, и в журнале владельца.
STATUS_CLEAN = 'clean'
STATUS_ISSUES = 'issues'
STATUS_BAD = 'bad'

STATUSES = (STATUS_CLEAN, STATUS_ISSUES, STATUS_BAD)

STATUS_LABELS = {
    STATUS_CLEAN: 'Чисто',
    STATUS_ISSUES: 'Замечания',
    STATUS_BAD: 'Плохо',
}

# Проблемы строки журнала.
PROBLEM_NOT_MARKED = 'not_marked'

PROBLEM_LABELS = {
    PROBLEM_NOT_MARKED: 'не отмечено',
}

# «Одна строка, что не так». Потолок — против случайной вставки простыни текста
# из мессенджера: журнал читается таблицей, и абзац в ячейке ломает чтение.
# 200 символов — это примерно две строки на телефоне.
NOTE_MAX_LEN = 200

# Дата, с которой вопрос задаётся. До неё дни пробелами НЕ считаются (см.
# докстроку модуля). Меняется только осознанно: сдвиг назад покрасит в «не
# отмечено» дни, когда вопроса ещё не было.
#
# Не 23-е, хотя код написан 23-го: на прод он приехал в 00:13 МСК 24-го, то есть
# 23 августа вопроса на экране не было НИ МИНУТЫ рабочего дня. Отсечка — первый
# день, когда на вопрос физически можно было ответить, иначе журнал открылся бы
# четырьмя пробелами, в которых никто не виноват.
RULE_FROM = '2026-08-24'


def normalize_note(text) -> str:
    """Свободный ввод -> одна строка: переносы и повторные пробелы схлопнуты.

    «Одна строка» — требование к данным, а не просьба к бармену: он пишет в
    <input>, но текст может прилететь вставкой из мессенджера с переносами.
    Схлопываем здесь, а не в CSS, чтобы в БД и в выгрузке лежало то же, что на
    экране.
    """
    if text is None:
        return ''
    return ' '.join(str(text).split())


def validate(status, note, has_photo: bool) -> Tuple[bool, Optional[str], Dict]:
    """Проверить ответ. -> (ok, текст_ошибки, {'status', 'note'}).

    Правила ровно те, что видит бармен на экране:
      * `clean` — ни строки, ни фото (заполненное поле = ответ не про «чисто»);
      * `issues` — строка обязательна, фото по желанию;
      * `bad` — обязательны и строка, и фото.

    `has_photo` — есть ли фото в итоге (новое загруженное ИЛИ сохранённое от
    предыдущего ответа): при правке опечатки в тексте нельзя заставлять бармена
    переснимать фотографию.
    """
    if status not in STATUSES:
        return False, 'Неизвестный ответ: ожидается «чисто», «замечания» или «плохо»', {}

    clean_note = normalize_note(note)

    if status == STATUS_CLEAN:
        if clean_note:
            return False, ('Ответ «Чисто» — без комментария. Если есть что сказать, '
                           'это «Замечания»'), {}
        if has_photo:
            return False, ('Ответ «Чисто» — без фото. Если есть что показать, '
                           'это «Замечания» или «Плохо»'), {}
        return True, None, {'status': status, 'note': None}

    if not clean_note:
        label = STATUS_LABELS[status]
        return False, f'Ответ «{label}» — напишите одной строкой, что не так', {}
    if len(clean_note) > NOTE_MAX_LEN:
        return False, (f'Слишком длинно: не больше {NOTE_MAX_LEN} символов '
                       f'(сейчас {len(clean_note)})'), {}

    if status == STATUS_BAD and not has_photo:
        return False, 'Ответ «Плохо» — нужно фото: без него это слово против слова', {}

    return True, None, {'status': status, 'note': clean_note}


def can_answer(shift_date, today) -> Tuple[bool, Optional[str]]:
    """Можно ли отвечать на приёмку смены сегодня. -> (ok, причина_отказа).

    Окно — ровно день смены по Москве (см. докстроку модуля). Обе даты в ISO.
    """
    date_str = str(shift_date or '')[:10]
    if not date_str:
        return False, 'У смены нет даты'
    if date_str == today:
        return True, None
    if date_str > today:
        return False, 'Смена ещё не наступила — приёмка отмечается в день смены'
    return False, 'Приёмка отмечается в день смены. Этот день уже закрыт'


def is_opening_shift(shift: Dict, shifts: List[Dict]) -> bool:
    """Открывающая ли это смена своего дня на своей точке (кто отвечает)."""
    ids = opening_shifts(shifts)
    return ids.get((shift.get('location_id'), shift.get('date'))) == shift.get('id')


def build_journal(shifts, acceptances, today, rule_from=RULE_FROM) -> Dict:
    """Собрать журнал приёмок: строка на каждую открывающую смену периода.

    Аргументы:
      shifts      — смены периода (`ShiftsManager.get_shifts_for_period`);
      acceptances — приёмки периода (`get_bar_acceptances_for_period`);
      today       — ISO-дата «сегодня» (параметром, чтобы тесты были
                    детерминированными): сегодняшний день без ответа — ещё не
                    пробел, смена могла не начаться;
      rule_from   — ISO-дата начала действия правила.

    Возвращает {'rows': [...], 'totals': {...}, 'locations': [...]}.
    Строки — по возрастанию даты, внутри дня по точке.
    """
    by_shift = {a.get('shift_id'): a for a in (acceptances or [])}
    opening_ids = set(opening_shifts(shifts).values())

    rows = []
    for s in shifts or []:
        if s.get('id') not in opening_ids:
            continue
        date_str = s.get('date') or ''
        acc = by_shift.get(s.get('id'))
        status = acc.get('status') if acc else None
        # Пробел: день прошёл, правило действовало, ответа нет. Сегодня и будущее
        # пробелом не считаются — смена ещё может ответить.
        expected = rule_from <= date_str < today
        problems = [PROBLEM_NOT_MARKED] if (expected and not acc) else []
        created = (acc or {}).get('created_at')
        updated = (acc or {}).get('updated_at')

        rows.append({
            'shift_id': s.get('id'),
            'date': date_str,
            'location_id': s.get('location_id'),
            'location_short': s.get('location_short') or s.get('location_name') or '',
            'location_name': s.get('location_name') or '',
            'employee_id': s.get('employee_id'),
            'employee_name': s.get('employee_name') or '',
            'start_time': s.get('start_time'),
            'status': status,
            'status_label': STATUS_LABELS.get(status),
            'note': (acc or {}).get('note'),
            'photo': (acc or {}).get('photo'),
            'answered_at': created,
            # «изменено»: ответ переписан в тот же день поверх первого.
            'edited': bool(created and updated and updated != created),
            'author_name': (acc or {}).get('author_name'),
            'expected': expected,
            'problems': problems,
        })

    rows.sort(key=lambda r: (r['date'], r['location_short'], r['shift_id'] or 0))

    totals = {
        'shifts': len(rows),
        'answered': sum(1 for r in rows if r['status']),
        STATUS_CLEAN: sum(1 for r in rows if r['status'] == STATUS_CLEAN),
        STATUS_ISSUES: sum(1 for r in rows if r['status'] == STATUS_ISSUES),
        STATUS_BAD: sum(1 for r in rows if r['status'] == STATUS_BAD),
        PROBLEM_NOT_MARKED: sum(1 for r in rows if PROBLEM_NOT_MARKED in r['problems']),
        'with_photo': sum(1 for r in rows if r['photo']),
    }

    # Точки — в порядке id (как в графике), только те, что есть в периоде.
    seen, locations = set(), []
    for r in sorted(rows, key=lambda r: (r['location_id'] or 0)):
        if r['location_id'] is None or r['location_id'] in seen:
            continue
        seen.add(r['location_id'])
        locations.append({'id': r['location_id'], 'short': r['location_short'],
                          'name': r['location_name']})

    return {'rows': rows, 'totals': totals, 'locations': locations}

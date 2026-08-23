"""
Чистота: приёмка бара на открытии смены — страница `/cleanliness` и API.

## Что это

Вопрос «Как принял бар?» на `/me` и журнал ответов для владельца. Правила (кто
отвечает, что обязательно, когда можно, что считать пробелом) живут в
`core/bar_acceptance.py`; хранение фото — в `core/bar_photo_store.py`. Здесь
только HTTP: права, разбор запроса, ответы.

## Права

Смотреть журнал — всем, как любую бизнес-страницу (принцип компании: равные
права). Отвечать на приёмку — ТОЛЬКО сам бармен этой смены, и админ тоже не
может: ценность записи в том, что каждая строка — свидетельство от первого лица.
Возможность проставить ответ за другого превратила бы журнал в то же самое
«мне сказали, что бар был грязный», от чего он и должен избавить. Забыли
ответить — день остаётся «не отмечено», и это честнее подставленного «Чисто».

Личность — только `users.employee_iiko_id` (та же привязка, на которой стоит
`/me`): сравнивается напрямую с `shifts.employee_id`. По имени не ищем нигде.

## Время

«Сегодня» берётся по Москве (`core/msk_time`), а не наивным `date.today()`: в
прод-образе нет системного tzdata, и наивная дата с 00:00 до 03:00 МСК отстаёт
на календарный день. Для окна «ответить можно в день смены» это означало бы, что
бармен ночной точки не может ответить за свой же день.

## Файлы

| Файл | Роль |
|------|------|
| `routes/cleanliness.py` | этот модуль |
| `core/bar_acceptance.py` | правила и сборка журнала |
| `core/bar_photo_store.py` | фото на диске |
| `core/shifts_manager.py` | таблица `bar_acceptance` (схема v11) |
| `templates/cleanliness.html`, `static/cleanliness/*`, `static/js/cleanliness/*` | журнал владельца |
| `templates/me.html`, `static/js/me/acceptance.js` | карточка вопроса у бармена |

Подробнее — `docs/cleanliness.md`.

## Changelog

- 2026-08-23 — модуль создан.
"""

from datetime import date, timedelta

from flask import (Blueprint, jsonify, render_template, request,
                   send_from_directory)

from core import bar_photo_store as photos
from core import msk_time
from core.auth_guard import current_user
from core.bar_acceptance import (NOTE_MAX_LEN, PROBLEM_LABELS, RULE_FROM,
                                 STATUS_LABELS, build_journal, can_answer,
                                 validate)
from core.cash_register import opening_shifts
from extensions import APP_VERSION, shifts_mgr

cleanliness_bp = Blueprint('cleanliness', __name__)


def _today() -> str:
    """Текущий РАБОЧИЙ день бара в ISO — см. раздел «Время» в докстроке модуля.

    Не календарная дата: смена, идущая через полночь, остаётся сегодняшней до
    06:00 МСК. Иначе бармен, открывший бар в 10:00, терял право поправить свою
    же приёмку в 00:30 — он ещё на смене, а окно «в день смены» уже закрылось.
    """
    return msk_time.business_today().isoformat()


def _can_answer_window(shift_date):
    """Окно ответа со «сегодня» по Москве. Отдельной функцией, чтобы дата
    бралась в одном месте и её было чем подменить в тестах."""
    return can_answer(shift_date, _today())


def _valid_month(year, month) -> bool:
    return 2020 <= year <= 2100 and 1 <= month <= 12


def _month_bounds(year, month):
    first = date(year, month, 1)
    last = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) \
        - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def _labels_payload() -> dict:
    """Подписи и лимиты — одним куском для обоих фронтов, чтобы формулировка
    ответа в карточке бармена и в журнале владельца не разъехалась."""
    return {
        'status_labels': STATUS_LABELS,
        'problem_labels': PROBLEM_LABELS,
        'note_max_len': NOTE_MAX_LEN,
        'photo_max_bytes': photos.MAX_PHOTO_BYTES,
        'rule_from': RULE_FROM,
    }


def _shift_public(shift: dict) -> dict:
    """Смена для фронта — только то, что нужно карточке приёмки."""
    return {
        'id': shift.get('id'),
        'date': shift.get('date'),
        'start_time': shift.get('start_time'),
        'location_id': shift.get('location_id'),
        'location_name': shift.get('location_name'),
        'location_short': shift.get('location_short'),
        'employee_id': shift.get('employee_id'),
        'employee_name': shift.get('employee_name'),
    }


def _acceptance_public(acc) -> dict:
    """Приёмка для фронта. `prev_photo` (служебное поле записи) не отдаём."""
    if not acc:
        return None
    return {
        'status': acc.get('status'),
        'status_label': STATUS_LABELS.get(acc.get('status')),
        'note': acc.get('note'),
        'photo': acc.get('photo'),
        'answered_at': acc.get('created_at'),
        'updated_at': acc.get('updated_at'),
        'edited': bool(acc.get('created_at') and acc.get('updated_at')
                       and acc.get('created_at') != acc.get('updated_at')),
        'author_name': acc.get('author_name'),
    }


# ==================== Страница ====================

@cleanliness_bp.route('/cleanliness')
def cleanliness_page():
    """Журнал приёмок. Данные подтягивает фронт: `/api/cleanliness/month/...`."""
    return render_template('cleanliness.html', app_version=APP_VERSION)


# ==================== Карточка бармена на /me ====================

@cleanliness_bp.route('/api/cleanliness/today', methods=['GET'])
def cleanliness_today():
    """Моя сегодняшняя приёмка: открывающая смена + ответ на неё, если есть.

    Идентификатор сотрудника в запросе НЕ принимается — только сессия: иначе
    любой залогиненный отметил бы приёмку за другого по номеру в URL.

    Отвечает 200 всегда: «аккаунт не привязан», «сегодня нет открывающей смены» —
    это статусы, а не ошибки. Фронт при них просто не рисует карточку.

    Кто открывающий, решает сервер (`opening_shifts`), а не клиент: продублировать
    это правило в JS означало бы завести вторую версию «кто отвечает за день».
    """
    user = current_user() or {}
    emp_id = (user.get('employee_iiko_id') or '').strip()
    today = _today()
    payload = {'today': today, 'items': [], **_labels_payload()}

    if not emp_id:
        payload['status'] = 'not_linked'
        payload['message'] = ('Аккаунт не привязан к сотруднику — попросите '
                              'администратора связать его на /admin/users.')
        return jsonify(payload)

    shifts = shifts_mgr.get_shifts_for_period(today, today)
    opening_ids = set(opening_shifts(shifts).values())
    mine = [s for s in shifts
            if s.get('id') in opening_ids and (s.get('employee_id') or '') == emp_id]

    if not mine:
        # Смена сегодня есть, но открывает не он (второй дневной бармен) — или
        # смены нет вовсе. Для карточки это одно и то же: вопрос не его.
        payload['status'] = 'no_shift'
        return jsonify(payload)

    payload['status'] = 'ok'
    for shift in mine:
        payload['items'].append({
            'shift': _shift_public(shift),
            'acceptance': _acceptance_public(shifts_mgr.get_bar_acceptance(shift['id'])),
        })
    return jsonify(payload)


@cleanliness_bp.route('/api/cleanliness/shift/<int:shift_id>', methods=['POST'])
def cleanliness_answer(shift_id):
    """Записать приёмку смены. multipart/form-data (с фото) или JSON (без).

    Поля: `status` (clean|issues|bad), `note`, `photo` (файл), `keep_photo`
    («оставить прежнее фото» при правке текста — чтобы не заставлять переснимать).

    Порядок проверок важен: сначала права и окно, потом содержимое файла, потом
    правила ответа — и только затем запись на диск. Иначе отклонённый ответ
    оставлял бы в каталоге осиротевшую фотографию.
    """
    # Отсекаем гигантское тело ДО чтения: Flask читает форму целиком в память.
    if (request.content_length or 0) > photos.MAX_PHOTO_BYTES + 64 * 1024:
        mb = photos.MAX_PHOTO_BYTES // (1024 * 1024)
        return jsonify({'error': f'Фото больше {mb} МБ'}), 413

    shift = shifts_mgr.get_shift(shift_id)
    if not shift:
        return jsonify({'error': 'Смена не найдена'}), 404

    user = current_user() or {}
    emp_id = (user.get('employee_iiko_id') or '').strip()
    if not emp_id:
        return jsonify({'error': 'Аккаунт не привязан к сотруднику — попросите '
                                 'администратора связать его на /admin/users'}), 403
    if (shift.get('employee_id') or '') != emp_id:
        # Осознанно без исключения для админа — см. раздел «Права» в докстроке.
        return jsonify({'error': 'Приёмку отмечает только бармен этой смены'}), 403

    ok_window, why = _can_answer_window(shift.get('date'))
    if not ok_window:
        return jsonify({'error': why}), 403

    day_shifts = shifts_mgr.get_shifts_for_period(shift['date'], shift['date'])
    if opening_shifts(day_shifts).get((shift.get('location_id'), shift.get('date'))) \
            != shift_id:
        return jsonify({'error': 'Бар принимает открывающая смена точки'}), 400

    form = request.form if request.form else (request.get_json(silent=True) or {})
    status = (form.get('status') or '').strip()
    note = form.get('note')
    keep_photo = str(form.get('keep_photo') or '').strip().lower() in ('1', 'true', 'on')

    prev = shifts_mgr.get_bar_acceptance(shift_id)
    prev_photo = (prev or {}).get('photo')

    # Содержимое файла проверяем в памяти, на диск ещё не пишем.
    upload = request.files.get('photo')
    data = upload.read() if upload else None
    if data:
        ok_photo, err = photos.check(data)
        if not ok_photo:
            return jsonify({'error': err}), 400

    kept = bool(keep_photo and prev_photo and photos.exists(prev_photo))
    ok, err, clean = validate(status, note, has_photo=bool(data) or kept)
    if not ok:
        return jsonify({'error': err}), 400

    photo_name = prev_photo if kept else None
    if data:
        saved, name_or_err = photos.save(data, shift['date'], shift_id)
        if not saved:
            return jsonify({'error': name_or_err}), 400
        photo_name = name_or_err

    row = shifts_mgr.set_bar_acceptance(
        shift_id,
        date=shift['date'],
        location_id=shift.get('location_id'),
        employee_id=shift.get('employee_id'),
        employee_name=shift.get('employee_name'),
        status=clean['status'],
        note=clean['note'],
        photo=photo_name,
        author_login=user.get('login'),
        author_name=user.get('display_name') or user.get('login'),
    )

    # Прежнее фото осиротело (ответ сменили на «Чисто» или переснял) — убираем.
    old = row.get('prev_photo')
    if old and old != photo_name:
        photos.delete(old)

    return jsonify({'ok': True, 'acceptance': _acceptance_public(row)})


# ==================== Журнал владельца ====================

@cleanliness_bp.route('/api/cleanliness/month/<int:year>/<int:month>', methods=['GET'])
def cleanliness_month(year, month):
    """Журнал приёмок за месяц: строка на каждую открывающую смену + итоги.

    Фильтрация и поиск — на фронте: месяц это ~120 строк (4 точки x 30 дней),
    гонять запрос на каждый щелчок фильтра незачем (как в кассовом регистре).
    """
    if not _valid_month(year, month):
        return jsonify({'error': 'Некорректный год или месяц'}), 400
    date_from, date_to = _month_bounds(year, month)

    journal = build_journal(
        shifts_mgr.get_shifts_for_period(date_from, date_to),
        shifts_mgr.get_bar_acceptances_for_period(date_from, date_to),
        today=_today(),
    )
    journal.update({
        'date_from': date_from,
        'date_to': date_to,
        'today': _today(),
        **_labels_payload(),
    })
    return jsonify(journal)


@cleanliness_bp.route('/api/cleanliness/photo/<name>', methods=['GET'])
def cleanliness_photo(name):
    """Отдать фотографию приёмки. Имя проверяется формой (`is_valid_name`) до
    любого обращения к диску — конкатенации пользовательской строки с путём нет.

    `nosniff` + явный mimetype: браузер не должен пытаться угадать тип файла,
    который загрузил пользователь. Кэш приватный: фото — внутренний документ.
    """
    if not photos.is_valid_name(name):
        return jsonify({'error': 'Фото не найдено'}), 404
    if not photos.exists(name):
        return jsonify({'error': 'Фото не найдено'}), 404
    resp = send_from_directory(photos.photo_dir(), name, mimetype='image/jpeg')
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, max-age=86400'
    return resp

"""
Личная страница `/me` — всё про одного человека: смена, месяц, показатели, KPI, деньги.

## Что это

Точка входа для бармена. Права при этом НЕ ограничены: все страницы остаются
доступны всем (принцип компании), `/me` просто убирает необходимость идти на
`/schedule`, потом на `/salary`, потом на `/employee` и на каждой заново
выбирать себя и период.

## Две свежести данных на одной странице

- **Живое** — смены, часы факта, календарь, действия «закрыть смену» и
  «запросить выходной». Рисуется на клиенте тем же кодом, что мобильный экран
  графика (`static/js/schedule/screens.js::renderMyShifts` поверх
  `window.Schedule`), и данные берёт из тех же `/api/schedule/*`. Сознательно НЕ
  дублируется здесь: два независимых расчёта «смены 8/15» разъехались бы, а
  правило дизайн-системы требует, чтобы обе версии строились из одних данных.
- **Снимок** — показатели, KPI и деньги. Считается раз в сутки для всех сразу
  (`core/me_snapshot.py`), читается с тома. Здесь только резолв «кто это» и
  выдача его строки.

Поэтому `/api/me` отдаёт `identity` + `snapshot` + три блока цифр, а живые блоки
не отдаёт вовсе.

## Безопасность

Единственный вход идентичности — сессия: `current_user()['employee_iiko_id']`.
Параметра «покажи сотрудника X» у эндпоинта НЕТ и быть не должно — иначе любой
залогиненный получил бы чужую зарплату по номеру в URL. Все решения о том, чьи
данные показать, принимает `core/me_identity.resolve_me`; любой отказ приходит
статусом с человеческим текстом, а не нулями.

## Файлы

| Файл | Роль |
|------|------|
| `routes/me.py` | этот модуль: страница + `GET /api/me` |
| `core/me_identity.py` | резолвер личности и статусы отказа |
| `core/me_snapshot.py` | чтение снимка, нормы, метаданные свежести |
| `templates/me.html`, `static/me/me.css`, `static/js/me/*` | фронт |
| `tests/test_me_routes.py` | тесты |

## Changelog

- 2026-08-13 — страница создана: живые блоки + каркас под снимок.
"""

from flask import Blueprint, current_app, jsonify, render_template, request

from core import me_snapshot
from core.auth_guard import current_user
from core.auth_manager import get_auth_manager
from core.me_identity import REFUSING_STATUSES, resolve_me
from extensions import APP_VERSION, shifts_mgr

me_bp = Blueprint('me', __name__)


# Подписи, объясняющие смысл цифр. Держим на сервере, а не в шаблоне: те же
# формулировки уходят в документацию и не должны разъезжаться между экраном и
# инструкцией. Требование принципа №1 проекта (.claude/CLAUDE.md): показывать
# пользователю, как посчитано.
NOTES = {
    'accrued_to_date': ('Суммы — начислено на сегодня по закрытым сменам. '
                        'Прогноза на конец месяца здесь нет.'),
    'excel': ('Отпуск, доп доход и вычеты по инвентаризации владелец ведёт в '
              'Excel — в этот итог они не входят.'),
    'hours_sources': ('В «Показателях» часы — из кассовых смен iiko, в «Деньгах» — '
                      'из факта, который вы вводите в конце смены. Это разные числа.'),
    'live_vs_snapshot': ('Смены и часы — живые. Показатели, KPI и деньги — снимок: '
                         'они пересчитываются раз в сутки.'),
}


@me_bp.route('/me')
def me_page():
    """Личная страница. Данные подтягивает фронт: `/api/me` + `/api/schedule/*`."""
    return render_template('me.html', app_version=APP_VERSION)


@me_bp.route('/api/me', methods=['GET'])
def api_me():
    """Личные данные текущего пользователя за месяц.

    `?month=YYYY-MM` — необязателен, по умолчанию текущий московский месяц.
    Отвечает 200 почти всегда: «привязки нет», «снимка нет», «в снимке нет
    меня» — это статусы в `identity`/`snapshot`, а не ошибки. 400 только на
    заведомо неверный `month`, 401 без входа (общий гейт).

    Идентификатор сотрудника в запросе не принимается — см. докстроку модуля.
    """
    month = request.args.get('month') or me_snapshot.current_month()
    if not me_snapshot.valid_month(month):
        return jsonify({'error': "month обязателен в формате YYYY-MM"}), 400

    user = current_user() or {}
    snapshot = me_snapshot.read_month(month)
    meta = me_snapshot.snapshot_meta(snapshot)

    identity = resolve_me(
        user, snapshot, month=_month_label(month),
        registry=_registry(),
        linked_users=_linked_users(user.get('employee_iiko_id')),
    )

    row = identity.get('row') or {}
    show_numbers = identity['status'] not in REFUSING_STATUSES

    return jsonify({
        'user': {
            'login': user.get('login'),
            'display_name': user.get('display_name'),
            'short_label': user.get('short_label'),
            'employee_iiko_id': user.get('employee_iiko_id'),
            'is_admin': bool(user.get('is_admin')),
        },
        'identity': {
            'status': identity['status'],
            'employee_id': identity['employee_id'],
            'employee_name': identity['employee_name'],
            'message': identity['message'],
            'issues': identity['issues'],
        },
        'month': month,
        'month_label': _month_label(month),
        'months_available': me_snapshot.available_months(),
        'today': me_snapshot.msk_today().isoformat(),
        'norms': snapshot.get('norms') or me_snapshot.norms(),
        'rates': snapshot.get('rates') or {},
        'kpi_meta': snapshot.get('kpi_meta') or {},
        'snapshot': meta,
        'metrics': row.get('metrics') if show_numbers else None,
        'kpi': row.get('kpi') if show_numbers else None,
        'money': row.get('money') if show_numbers else None,
        # Часы по ролям — для формулы «роль N ч x ставка» в блоке денег.
        # Отдельным полем, а не внутри money: money — это суммы, а это их основание.
        'hours': row.get('hours') if show_numbers else None,
        'notes': NOTES,
        'refresh': {
            'can_refresh': _iiko_configured()[0],
            'running': bool(me_snapshot.get_progress().get('running')),
            'cooldown_left_sec': me_snapshot.cooldown_left_sec(),
            'cooldown_min': me_snapshot.COOLDOWN_MIN,
            'last_error': me_snapshot.read_refresh_state().get('last_error'),
        },
    })


@me_bp.route('/api/me/refresh', methods=['POST'])
def api_me_refresh():
    """Пересчитать снимок сейчас. Фоновый прогон, ответ сразу.

    Права — у ВСЕХ вошедших, а не только у админа. Аргументы: (а) кнопка общая
    по решению владельца; (б) `admin_required` оставил бы бармена с устаревшим
    снимком без выхода — а повод обновить есть именно у него (внёс часы, ждёт
    пересчёт премии); (в) стоимость уже ограничена локом и кулдауном: чаще
    одного прогона в 30 минут на всю компанию не выйдет, сколько бы людей ни
    нажимало; (г) каждое нажатие попадает в журнал графика с логином.

    Ответы: 202 запущено | 409 идёт/кулдаун | 503 iiko не настроен.
    """
    ok, why = _iiko_configured()
    if not ok:
        return jsonify({'started': False, 'error': why}), 503

    started, reason, info = me_snapshot.start_background_refresh(
        current_app._get_current_object(), tag=_refresh_tag())
    if not started:
        payload = {'started': False, 'reason': reason}
        payload.update(info or {})
        if reason == 'cooldown':
            payload['error'] = ('Пересчёт можно запускать раз в '
                                f'{me_snapshot.COOLDOWN_MIN} минут — он общий для всех.')
        else:
            payload['error'] = 'Пересчёт уже идёт. Обычно занимает 1-2 минуты.'
        return jsonify(payload), 409

    _audit('me_snapshot_refresh',
           'Пересчёт личных показателей запущен вручную')
    return jsonify({'started': True, 'progress': info.get('progress')}), 202


@me_bp.route('/api/me/refresh-status', methods=['GET'])
def api_me_refresh_status():
    """Прогресс пересчёта и даты снимков — для поллинга кнопкой."""
    months = {}
    for m in me_snapshot.available_months():
        snap = me_snapshot.read_month(m)
        if snap:
            months[m] = {'refreshed_at': snap.get('_refreshed_at'),
                         'refreshed_by': snap.get('_refreshed_by'),
                         'source_status': snap.get('_source_status') or {}}
    state = me_snapshot.read_refresh_state()
    return jsonify({
        'progress': me_snapshot.get_progress(),
        'months': months,
        'cooldown_left_sec': me_snapshot.cooldown_left_sec(),
        'last_error': state.get('last_error'),
        'last_finished_at': state.get('last_finished_at'),
    })


# --- вспомогательное ---


def _iiko_configured():
    """Есть ли креды iiko. Без них прогон гарантированно бесполезен -> 503.

    Проверяем ДО взятия лока и до записи состояния: иначе кнопка «съедала» бы
    кулдаун на прогоне, который всё равно ничего не посчитает.
    """
    try:
        import config
        if (config.IIKO_LOGIN or '').strip() and (config.IIKO_PASSWORD or '').strip():
            return True, ''
    except Exception as e:
        return False, f'Настройки iiko недоступны: {e}'
    return False, 'iiko не настроен (IIKO_LOGIN / IIKO_PASSWORD) — пересчёт невозможен'


def _refresh_tag():
    u = current_user() or {}
    return 'manual:' + (u.get('login') or 'unknown')


def _audit(action, summary):
    """Журнал графика, best-effort: сбой журнала не должен валить операцию.
    Тот же приём, что _audit в routes/salary.py."""
    try:
        u = current_user() or {}
        shifts_mgr.log_audit(
            action=action,
            summary=summary,
            actor_login=u.get('login'),
            actor_name=u.get('display_name') or u.get('login') or 'неизвестно',
        )
    except Exception as e:
        print(f"[ME AUDIT WARNING] zhurnal ne zapisan ({action}): {e}")

MONTH_NAMES_GEN = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль',
                   'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']


def _month_label(month: str) -> str:
    """'2026-08' -> 'август 2026' для текстов сообщений."""
    try:
        year, mon = int(month[:4]), int(month[5:7])
        return f'{MONTH_NAMES_GEN[mon - 1]} {year}'
    except (ValueError, IndexError):
        return month


def _registry():
    """Реестр сотрудников графика, best-effort.

    Пустой список означает «не смогли прочитать», и резолвер это учитывает: он
    не объявляет привязку ошибочной из-за недоступной shifts.db.
    """
    try:
        return shifts_mgr.get_schedule_employees(include_inactive=True)
    except Exception as e:
        print(f"[ME WARNING] reestr sotrudnikov nedostupen: {e}")
        return []


def _linked_users(employee_iiko_id):
    """Аккаунты, привязанные к этому сотруднику — для проверки двойной привязки.

    Сбой чтения auth.db не должен ронять страницу, но и «дублей нет» из-за
    ошибки утверждать нельзя: возвращаем пустой список, и тогда резолвер просто
    не сможет обнаружить дубль — при этом сам дубль всё равно виден админу
    баннером на /admin/users и строкой в логе при старте.
    """
    if not employee_iiko_id:
        return []
    try:
        return get_auth_manager().list_users_by_employee_id(employee_iiko_id)
    except Exception as e:
        print(f"[ME WARNING] proverka dvoynoy privyazki ne udalas: {e}")
        return []

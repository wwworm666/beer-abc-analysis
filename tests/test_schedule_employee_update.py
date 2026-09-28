# -*- coding: utf-8 -*-
"""
PUT /api/schedule/employee/<iiko_id> — правка реестра сотрудников графика (2026-09-28).

Ошибка до правки: тело без полей (или с одними null) доходило до менеджера, тот не
находил, что обновлять, и маршрут отвечал 404 «Сотрудник не найден» — хотя сотрудник
есть. Кривые типы давали 500 (число в short_label — AttributeError на .strip(),
буквы в sort_order — ValueError на int()), а строка 'false' в active ВКЛЮЧАЛА показ.

Теперь: нет полей — 400 «Нечего менять», неверный тип — 400 с понятным текстом,
404 — только когда такого iiko_id нет в реестре. Формат редактора графика (active 1/0,
sort_order числом) и MCP (active true/false) работает как раньше.

Данные — временная shifts.db; пользователь подменён. Запуск:
py -3 -m pytest -q tests/test_schedule_employee_update.py
"""

import pytest
from flask import Flask

from core.shifts_manager import ShiftsManager


@pytest.fixture
def api(tmp_path, monkeypatch):
    import core.auth_guard as guard
    import routes.schedule as sched

    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    mgr.sync_employees([('guid-1', 'Иван Петров')])   # без смен — добавлен скрытым
    monkeypatch.setattr(sched, 'shifts_mgr', mgr)
    user = {'login': 'owner', 'display_name': 'Владелец', 'is_admin': True}
    monkeypatch.setattr(guard, '_load_user', lambda: user)
    monkeypatch.setattr(sched, 'current_user', lambda: user)

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'
    app.register_blueprint(sched.schedule_bp)
    return app.test_client(), mgr


def _employee(mgr, emp_id='guid-1'):
    return next(e for e in mgr.get_schedule_employees(include_inactive=True)
                if e.get('id') == emp_id)


def test_empty_body_is_400_not_404(api):
    client, _mgr = api
    for body in ({}, {'short_label': None, 'active': None}, None):
        response = client.put('/api/schedule/employee/guid-1', json=body)
        assert response.status_code == 400, (body, response.get_json())
        assert 'Нечего менять' in response.get_json()['error']


def test_wrong_types_are_400(api):
    client, mgr = api
    before = _employee(mgr)
    for body, needle in (({'short_label': 5}, 'short_label'),
                         ({'active': 'false'}, 'active'),
                         ({'active': 2}, 'active'),
                         ({'sort_order': 'abc'}, 'sort_order'),
                         ({'sort_order': 2.5}, 'sort_order'),
                         ({'sort_order': True}, 'sort_order')):
        response = client.put('/api/schedule/employee/guid-1', json=body)
        assert response.status_code == 400, body
        assert needle in response.get_json()['error'], body
    assert _employee(mgr) == before, 'ничего не изменилось'
    assert client.put('/api/schedule/employee/guid-1', json=[1]).status_code == 400


def test_unknown_employee_is_404(api):
    client, _mgr = api
    response = client.put('/api/schedule/employee/guid-ghost', json={'short_label': 'ГП'})
    assert response.status_code == 404


def test_editor_and_mcp_formats_still_work(api):
    client, mgr = api
    assert client.put('/api/schedule/employee/guid-1',
                      json={'short_label': ' ИП '}).status_code == 200
    assert _employee(mgr)['short_label'] == 'ИП'
    # Редактор графика шлёт active 1/0 и sort_order числом, MCP — true/false.
    assert client.put('/api/schedule/employee/guid-1', json={'active': 0}).status_code == 200
    assert not _employee(mgr)['active']
    assert client.put('/api/schedule/employee/guid-1', json={'active': True}).status_code == 200
    assert _employee(mgr)['active']
    assert client.put('/api/schedule/employee/guid-1',
                      json={'sort_order': '7'}).status_code == 200
    assert _employee(mgr)['sort_order'] == 7
    assert client.put('/api/schedule/employee/guid-1',
                      json={'short_label': ''}).status_code == 200
    assert not _employee(mgr)['short_label'], 'пустая строка убирает сокращение'

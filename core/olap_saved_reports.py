"""Сохранённые отчёты конструктора (/explorer): кнопки «Сохранить» и «Открыть».

Что это
    Конфигурации отчётов, которые сохранили пользователи сервиса (и агенты по прямой
    просьбе владельца): тип отчёта, поля строк, столбцов и показателей, фильтры, период.
    Данных отчёта здесь нет — при открытии он строится заново из iiko. Период хранится
    либо пресетом («прошлый месяц» — каждый раз свой), либо явными датами.

Где лежит
    explorer_reports.json на постоянном диске (core/storage_paths.get_data_path;
    локально — data/explorer_reports.json). Запись — атомарная (core/json_store) под
    межпроцессным замком: в проде два воркера gunicorn.

Формат файла
    {"version": 1, "reports": [{"id", "name", "config", "created_at", "created_by",
    "updated_at", "updated_by"}, ...]}

Проверка при сохранении — структурная (типы, списки, пресет периода, операции
фильтров), без обращения к iiko: сохранение не должно зависеть от доступности сервера.
Поля против каталога проверяются при построении отчёта.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import ExitStack, contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import portalocker

from core import msk_time
from core.json_store import atomic_write_json, file_lock
from core.olap_catalog import REPORT_TYPES
from core.olap_constructor import (FILTER_OPS, MAX_COLUMN_FIELDS, MAX_FILTERS, MAX_MEASURES,
                                   MAX_ROW_FIELDS, PERIOD_PRESETS, ConstructorError)

FILE_NAME = 'explorer_reports.json'
MAX_REPORTS = 300
NAME_MAX = 120

_path_override: Optional[str] = None
_lock = threading.Lock()


def set_path(path: Optional[str]) -> None:
    """Тесты: работать с временным файлом. None — вернуть боевой путь."""
    global _path_override
    _path_override = path


def _path() -> str:
    if _path_override:
        return _path_override
    from core.storage_paths import get_data_path
    return get_data_path(FILE_NAME)


def _read(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {'version': 1, 'reports': []}
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        # Битый файл не молчит и не перетирается пустым: сохранение упадёт с ошибкой.
        raise ConstructorError('Файл сохранённых отчётов не читается: ' + str(error), status=500)
    if not isinstance(data, dict) or not isinstance(data.get('reports'), list):
        raise ConstructorError('Файл сохранённых отчётов в неверном формате.', status=500)
    return data


def list_reports() -> List[dict]:
    """Все сохранённые отчёты, свежие первыми."""
    with _lock:
        data = _read(_path())
    reports = [r for r in data['reports'] if isinstance(r, dict)]
    reports.sort(key=lambda r: r.get('updated_at') or '', reverse=True)
    return reports


def get_report(report_id: str) -> Optional[dict]:
    for report in list_reports():
        if report.get('id') == report_id:
            return report
    return None


def _day(raw: Any) -> Optional[str]:
    """Настоящая дата YYYY-MM-DD или None («2026-13-45» — не дата)."""
    if not isinstance(raw, str) or len(raw) != 10:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date().isoformat()
    except ValueError:
        return None


def _check_list(config: dict, key: str, limit: int) -> List[str]:
    value = config.get(key) or []
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ConstructorError('config.' + key + ': список id полей.')
    if len(value) > limit:
        raise ConstructorError('config.' + key + ': не больше ' + str(limit) + '.')
    return list(value)


def validate_config(config: Any) -> dict:
    """Проверить и нормализовать конфигурацию отчёта (без iiko)."""
    if not isinstance(config, dict):
        raise ConstructorError('config: нужен объект конфигурации отчёта.')
    report_type = str(config.get('report_type') or '').upper()
    if report_type not in REPORT_TYPES:
        raise ConstructorError('config.report_type: один из ' + ', '.join(REPORT_TYPES) + '.')
    rows = _check_list(config, 'rows', MAX_ROW_FIELDS)
    columns = _check_list(config, 'columns', MAX_COLUMN_FIELDS)
    measures = _check_list(config, 'measures', MAX_MEASURES)
    if not rows and not columns:
        raise ConstructorError('config: пустой отчёт — нет полей в строках и столбцах.')
    if not measures:
        raise ConstructorError('config: нет показателей.')
    filters = config.get('filters') or []
    if not isinstance(filters, list) or len(filters) > MAX_FILTERS:
        raise ConstructorError('config.filters: список до ' + str(MAX_FILTERS) + ' фильтров.')
    for index, item in enumerate(filters):
        if not isinstance(item, dict) or not isinstance(item.get('field'), str) or \
                item.get('op') not in FILTER_OPS:
            raise ConstructorError('config.filters[' + str(index) + ']: нужен {field, op} с op '
                                   'из ' + ', '.join(FILTER_OPS) + '.')
    # Умолчание — как у построения отчёта (olap_constructor.parse_spec): без флага
    # «не удалено» ставится автоматически. Страница всегда сохраняет true и фильтры
    # «не удалено» фишками; конфиг агента без флага страница откроет с этими фишками.
    include_deleted = config.get('include_deleted', False)
    if not isinstance(include_deleted, bool):
        raise ConstructorError('config.include_deleted: true или false.')
    period = config.get('period')
    if period is not None:
        if not isinstance(period, dict):
            raise ConstructorError('config.period: {"preset": …} или {"from": …, "to": …}.')
        if 'preset' in period:
            if period['preset'] not in PERIOD_PRESETS:
                raise ConstructorError('config.period.preset: один из ' +
                                       ', '.join(PERIOD_PRESETS) + '.')
            period = {'preset': period['preset']}
        else:
            start, end = _day(period.get('from')), _day(period.get('to'))
            if start is None or end is None or end < start:
                raise ConstructorError('config.period: from и to — даты YYYY-MM-DD, to не раньше from.')
            period = {'from': start, 'to': end}
    return {'report_type': report_type, 'rows': rows, 'columns': columns, 'measures': measures,
            'filters': filters, 'include_deleted': include_deleted, 'period': period}


@contextmanager
def _locked(path: str) -> Iterator[None]:
    """Замок записи: потоки процесса и воркеры gunicorn (межпроцессный замок-файл)."""
    with _lock, ExitStack() as stack:
        try:
            stack.enter_context(file_lock(path + '.lock'))
        except portalocker.exceptions.LockException:
            raise ConstructorError('Файл сохранённых отчётов занят другим сохранением — '
                                   'повторите через несколько секунд.', status=503, code='busy')
        yield


def _check_id(report_id: Any) -> str:
    if not isinstance(report_id, str) or not report_id:
        raise ConstructorError('id: строка — id сохранённого отчёта.')
    return report_id


def save_report(name: Any, config: Any, author: str, report_id: Optional[str] = None) -> dict:
    """Создать отчёт (report_id не задан) или заменить существующий. Возвращает запись."""
    name = ' '.join(str(name or '').split())
    if not name:
        raise ConstructorError('name: название отчёта не может быть пустым.')
    if len(name) > NAME_MAX:
        raise ConstructorError('name: не длиннее ' + str(NAME_MAX) + ' символов.')
    if report_id is not None:
        _check_id(report_id)
    clean = validate_config(config)
    now = msk_time.now().strftime('%Y-%m-%d %H:%M')
    path = _path()
    with _locked(path):
        data = _read(path)
        reports = [r for r in data['reports'] if isinstance(r, dict)]
        if report_id:
            record = next((r for r in reports if r.get('id') == report_id), None)
            if record is None:
                raise ConstructorError('Отчёт ' + report_id + ' не найден.', status=404,
                                       code='not_found')
            record.update(name=name, config=clean, updated_at=now, updated_by=author)
        else:
            if len(reports) >= MAX_REPORTS:
                raise ConstructorError('Сохранено уже ' + str(MAX_REPORTS) + ' отчётов — '
                                       'удалите ненужные.', status=409, code='too_many_reports')
            record = {'id': uuid.uuid4().hex[:12], 'name': name, 'config': clean,
                      'created_at': now, 'created_by': author, 'updated_at': now,
                      'updated_by': author}
            reports.append(record)
        data['reports'] = reports
        data['version'] = 1
        atomic_write_json(path, data)
    return record


def delete_report(report_id: str) -> dict:
    """Удалить отчёт; нет такого — ConstructorError 404."""
    _check_id(report_id)
    path = _path()
    with _locked(path):
        data = _read(path)
        reports = [r for r in data['reports'] if isinstance(r, dict)]
        record = next((r for r in reports if r.get('id') == report_id), None)
        if record is None:
            raise ConstructorError('Отчёт ' + str(report_id) + ' не найден.', status=404,
                                   code='not_found')
        data['reports'] = [r for r in reports if r.get('id') != report_id]
        atomic_write_json(path, data)
    return record

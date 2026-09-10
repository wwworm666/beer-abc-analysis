"""Один снимок сети для страниц остатков: остатки + операции за окно + номенклатура.

До 2026-09-10 каждый из пяти эндпоинтов /api/stocks/* сам открывал сессию iiko
и качал balance/stores и полный XML storeOperations, а фронт звал все пять
разом — пять сессий и четыре выгрузки на каждый выбор бара (S-07 в
docs/technical/audits/STOCKS_AUDIT_2026-09-10.md). Здесь снимок считается один
раз на процесс (2 воркера gunicorn — не больше двух сессий) и живёт
SNAPSHOT_TTL секунд; одновременные запросы ждут один fetch (single-flight в
extensions.cached_olap).

Сбой iiko не маскируется: если остатки или операции не получены или пусты
(четыре склада за 30 дней не бывают пустыми), снимка нет (None), он не
кэшируется, и эндпоинт обязан ответить ошибкой, а не нулями (S-08). Чтобы
пять параллельных запросов фронта не ждали друг за другом по таймауту iiko,
после неудачи следующие SNAPSHOT_FAIL_TTL секунд снимок сразу None.

Все даты снимка — московские (как timestamp в get_store_balances).
"""
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import extensions
from core.olap_reports import OlapReports
from core.nomenclature_xml import get_xml_nomenclature, merge_nomenclature
from core.stock_consumption import WINDOW_DAYS, format_period, period_bounds
from extensions import cached_olap, get_cached_nomenclature

# 120 с: остатки и обороты меняются медленно, TTL покрывает пять параллельных
# запросов фронта на один выбор бара и повторный клик «Обновить данные».
SNAPSHOT_TTL = 120
# 30 с: после неудачного похода в iiko не повторять его на каждый запрос
# (пять запросов фронта × ретраи, каждый с таймаутом авторизации до 90 с).
SNAPSHOT_FAIL_TTL = 30
SNAPSHOT_KEY = 'stock_snapshot_v1'
IIKO_TZ = ZoneInfo('Europe/Moscow')

_last_failure_at: Optional[float] = None


def _fetch_snapshot(window_days: int) -> Optional[dict]:
    olap = OlapReports()
    if not olap.connect():
        print("[SNAPSHOT] iiko connect failed")
        return None
    try:
        now = datetime.now(IIKO_TZ).replace(tzinfo=None)
        today = now.date()
        date_from, date_to = period_bounds(today, window_days)
        df, dt = format_period(date_from, date_to)
        balances = olap.get_store_balances()
        if not balances:
            print("[SNAPSHOT] balances unavailable or empty")
            return None
        operations = olap.get_store_operations_report(df, dt, None)
        if not operations:
            print("[SNAPSHOT] store operations unavailable or empty")
            return None
        return {
            'balances': balances,
            'operations': operations,
            'today': today.isoformat(),
            'date_from': df,
            'date_to': dt,
            'window_days': window_days,
            'fetched_at': now.isoformat(timespec='seconds'),
        }
    finally:
        olap.disconnect()


def _recently_failed() -> bool:
    return _last_failure_at is not None and (time.time() - _last_failure_at) < SNAPSHOT_FAIL_TTL


def get_stock_snapshot(window_days: int = WINDOW_DAYS, ttl: int = SNAPSHOT_TTL,
                       force: bool = False) -> Optional[dict]:
    """Снимок сети из кэша или свежий; None — iiko не отдал данные (не кэшируется).

    force=True сбрасывает кэш снимка и отрицательный кэш (кнопка «Обновить»).
    """
    global _last_failure_at
    if force:
        extensions.DASHBOARD_OLAP_CACHE.pop(SNAPSHOT_KEY, None)
        _last_failure_at = None
    elif _recently_failed():
        return None

    def fetch():
        # Выполняется под single-flight локом: ждавшие запросы после чужой
        # неудачи не ходят в iiko сами.
        if _recently_failed():
            return None
        return _fetch_snapshot(window_days)

    snapshot = cached_olap(SNAPSHOT_KEY, fetch, ttl=ttl)
    if snapshot is None:
        if _last_failure_at is None:
            _last_failure_at = time.time()
    else:
        _last_failure_at = None
    return snapshot


class _LazyOlap:
    """Подключается к iiko только если кэш номенклатуры (память/диск) пуст.

    Берёт только OLAP-вариант (свежие категории, товары с движением): полный
    список товаров даёт локальный XML в get_stocks_nomenclature, а XML-fallback
    самого iiko отдал бы parentId-GUID и лёг бы в дисковый кэш на сутки.
    """

    def get_nomenclature(self):
        olap = OlapReports()
        if not olap.connect():
            return None
        try:
            return olap.get_nomenclature_olap_only()
        finally:
            olap.disconnect()


def get_stocks_nomenclature() -> Optional[dict]:
    """OLAP-номенклатура (свежие категории, товары с движением) поверх полной XML.

    parentId у всех записей приводится к имени верхней группы: если OLAP-запись
    (или старый дисковый кэш) несёт GUID или неизвестную группу, а товар есть в
    XML, берётся верхняя группа из XML. Возвращает None, если нет ни того, ни другого.
    """
    olap_nomenclature = get_cached_nomenclature(_LazyOlap())
    xml_nomenclature = get_xml_nomenclature()
    merged = merge_nomenclature(olap_nomenclature, xml_nomenclature)
    if not merged:
        return None
    if xml_nomenclature:
        top_names = {rec.get('parentId') for rec in xml_nomenclature.values() if rec.get('parentId')}
        fixed = 0
        for pid, rec in merged.items():
            if rec.get('parentId') in top_names:
                continue
            xml_rec = xml_nomenclature.get(pid)
            if xml_rec and xml_rec.get('parentId') and xml_rec.get('parentId') != rec.get('parentId'):
                merged[pid] = {**rec, 'parentId': xml_rec['parentId']}
                fixed += 1
        if fixed:
            print(f"[SNAPSHOT] nomenclature: parentId normalized from XML for {fixed} products")
    return merged

from flask import Blueprint, request, jsonify
import re
import os
import sys
import json
import math
import subprocess
import threading
import time
from pathlib import Path
from datetime import date, datetime
from core.iiko_barcodes import get_barcode_map, invert_to_product_gtins
from core.dashboard_analysis import DashboardMetrics
from core.stock_consumption import INTERNAL_TRANSFER as INTERNAL_TRANSFER_TYPE, aggregate_consumption
from core.purchase_price import line_sum, resolve_prices
from core.stock_snapshot import get_stock_snapshot, get_stocks_nomenclature
from core.order_store import get_order_store
from core.supplier_directory import get_supplier_directory
from core.supplier_calendar import next_delivery_date, delivery_after
from extensions import taps_manager, BARS

_BASE_DIR = Path(__file__).resolve().parent.parent
_CHZ_CACHE_FILE = _BASE_DIR / 'chz_test' / 'debug' / 'chz_stock.json'
_CHZ_REFRESH_LOG = _BASE_DIR / 'chz_test' / 'debug' / 'refresh.log'
# Cross-worker lock-файл: gunicorn запускает 2 worker'а, у каждого свой _refresh_proc.
# Без файлового флага оба worker'а могут запустить refresh параллельно (race на refresh.log).
_CHZ_REFRESH_LOCK = _BASE_DIR / 'chz_test' / 'debug' / 'refresh.lock'
_refresh_proc: subprocess.Popen | None = None
_refresh_log_file = None
_refresh_lock = threading.Lock()

# Маппинги бар→склад→КПП — единственный источник для всех эндпоинтов файла (см. _resolve_bar).
_BAR_ID_MAP = {
    'Большой пр. В.О': 'bar1',
    'Лиговский': 'bar2',
    'Кременчугская': 'bar3',
    'Варшавская': 'bar4',
    'Общая': None,
}
_STORE_ID_MAP = {
    'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',
    'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',
    'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',
    'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',
}
_BAR_KPP_MAP = {
    'bar1': '780145001',
    'bar2': '781645001',
    'bar3': '784201001',
    'bar4': '781045001',
}

# Параметры поставщиков (срок поставки, кратность, дни доставки) — справочник
# core/supplier_directory.py, редактируемый на /suppliers (этап 3 редизайна);
# незаведённый поставщик получает DEFAULT_LEAD_TIME_DAYS (используется в тестах).

# Параметры формулы рекомендации к заказу
SAFETY_DAYS = 3                  # страховой запас сверх lead_time: колебания спроса и
                                 # задержка поставки на 1–2 дня (решение владельца 2026-09-10)
NEAR_EXPIRY_BLOCK_DAYS = 14      # если до конца срока годности < этого — не заказываем
NEAR_EXPIRY_WARN_DAYS = 30       # порог «горит» в Сроках годности: near_expiry_count и сортировка
DAYS_PER_WEEK = 7                # velocity и «в неделю» считаются от avg_sales × 7
SLOW_MOVER_WEEKLY_SALES = 1.0    # граница slow-mover'а: < 1 продажи в неделю (только штучные товары)
FAST_MOVER_WEEKLY_SALES = 7.0    # граница fast-mover'а: ≥ 7 продаж в неделю
PIECE_UNITS = ('шт',)            # «раз в неделю» имеет смысл только для штучного товара:
                                 # 0.9 кг соуса или 0.9 л в неделю — не «редко», а нормальный расход
STOCK_ZERO_EPS = 0.05            # |остаток| меньше этого — учётный ноль, не «отрицательный остаток»
# Добор до минимального заказа поставщика (docs/suppliers.md): горизонт группы
# растягивается не больше чем на столько дней сверх расчётного. 30 дней — окно расхода:
# дальше средний расход уже ничего не гарантирует, а товар месяц стоит на складе.
MIN_ORDER_MAX_EXTRA_DAYS = 30
# Кеги заказывают целыми бочками, а не литрами: «заказать 8 л» исполнить нельзя
# (решение владельца 2026-09-19). Объём берётся из названия номенклатуры
# («КЕГ Фуллерс ИПА 30 л»), а где его нет — DEFAULT_KEG_LITERS.
DEFAULT_KEG_LITERS = 30          # объём кеги по умолчанию (решение владельца 2026-09-19)
MIN_KEG_LITERS = 5               # меньше этого в названии — не объём кеги (0,5 л — это порция)
MAX_KEG_LITERS = 200             # больше этого — тоже не кега, а опечатка в названии
# Позиция без строки остатка в iiko попадает на доску по расходу за окно. Если
# последний расход был давно, сорт из ротации вышел: показываем, но не заказываем.
NO_STOCK_RECENT_DAYS = 7


def _supplier_params(supplier_name, view=None):
    """Параметры поставщика из справочника по имени или алиасу category.

    Возвращает {name, lead_time_days, pack_size, delivery_weekdays, self_pickup,
    is_default}; неизвестный поставщик получает умолчания (is_default = True).
    view — срез справочника на один запрос (get_supplier_directory().view()).
    """
    if view is None:
        view = get_supplier_directory().view()
    return dict(view.params(supplier_name))


_KEG_VOLUME_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*л\b', re.IGNORECASE)


def _keg_liters(name):
    """Объём кеги из названия номенклатуры; нет в названии — (DEFAULT_KEG_LITERS, 'default').

    «КЕГ Фуллерс ИПА 30 л» → (30.0, 'name'). Берётся последнее число перед «л»:
    в названии может стоять и крепость, и год. Значения вне
    MIN_KEG_LITERS..MAX_KEG_LITERS игнорируются — это не объём бочки.
    По номенклатуре на 2026-09: объём указан у 65 % разливных позиций, из них
    30 л и 20 л — почти все.
    """
    found = None
    for match in _KEG_VOLUME_RE.finditer(name or ''):
        try:
            value = float(match.group(1).replace(',', '.'))
        except ValueError:
            continue
        if MIN_KEG_LITERS <= value <= MAX_KEG_LITERS:
            found = value
    if found is None:
        return float(DEFAULT_KEG_LITERS), 'default'
    return found, 'name'


def _velocity(avg_sales, unit='шт'):
    """Классификация скорости расхода по 30-дневному среднему (единиц/день).

    Считаем в неделю (avg_sales × 7), это интуитивнее для бара:
        dead:    нет расхода за период (avg_sales = 0)
        slow:    < 1 штуки в неделю — раз в месяц/реже, не пополняем автоматически;
                 только для штучных единиц (PIECE_UNITS): для кг и л порог «1 в неделю»
                 бессмыслен, такие товары не бывают slow (с 2026-09-12)
        regular: 1–7 в неделю
        fast:    ≥ 7 в неделю
    """
    if avg_sales <= 0:
        return 'dead'
    weekly = avg_sales * DAYS_PER_WEEK
    if weekly < SLOW_MOVER_WEEKLY_SALES and (unit or 'шт') in PIECE_UNITS:
        return 'slow'
    if weekly < FAST_MOVER_WEEKLY_SALES:
        return 'regular'
    return 'fast'


def _calc_recommendation(stock, avg_sales, cover_days, pack_size, days_to_expiry, velocity):
    """Расчёт рекомендованного количества к заказу.

    target_stock = avg_sales * (cover_days + SAFETY_DAYS)
    deficit      = max(0, target_stock - stock)
    recommended  = ceil(deficit / pack_size) * pack_size

    cover_days — сколько дней должен покрыть заказ: до поставки, следующей за
    ближайшей (core/supplier_calendar.horizon_days). Заказ в четверг с поставкой
    в пятницу должен дожить до понедельника: 4 дня, а не 1 (с 2026-09-11, этап 2;
    раньше здесь был константный lead_time_days).

    pack_size — кратность заказа: упаковка для фасовки и кухни, объём кеги в
    литрах для разливного (может быть дробным: «29,3 л»). Целая кратность даёт
    целый результат, дробная — литры до сотых.

    Спецслучаи (рекомендация принудительно 0):
        velocity in ('dead', 'slow')       → не пополняем редко-продаваемые позиции
        0 <= days_to_expiry < 14           → расходуем то что есть на полке
    """
    if velocity in ('dead', 'slow'):
        return 0
    if avg_sales <= 0:
        return 0
    if days_to_expiry is not None and 0 <= days_to_expiry < NEAR_EXPIRY_BLOCK_DAYS:
        return 0
    target_stock = avg_sales * (cover_days + SAFETY_DAYS)
    deficit = target_stock - stock
    if deficit <= 0:
        return 0
    try:
        pack = float(pack_size)
    except (TypeError, ValueError):
        pack = 1.0
    if not math.isfinite(pack) or pack <= 0:
        pack = 1.0
    packs = math.ceil(deficit / pack)
    return int(packs * pack) if float(pack).is_integer() else round(packs * pack, 2)


def _recommend_at(row, extra_days):
    """Рекомендация позиции, если считать на extra_days дней дальше её горизонта.

    Те же правила, что у базового расчёта (_calc_recommendation): dead/slow и
    истекающая партия остаются нулём на любом горизонте — добор до минимального
    заказа не оживляет то, что заказывать нельзя. Сюда же попадает сорт, ушедший
    из ротации (row['blocked']): его нет в остатках и расхода давно не было.

    Отрицательный остаток заказ НЕ блокирует (решение владельца 2026-09-19):
    минус означает, что товара на полке точно нет, и заказать надо полную цель.
    Полка при этом считается пустой, а не «минус три»: недостачу заказом не
    закрывают, её ищут в учёте.
    """
    if row['blocked']:
        return 0
    return _calc_recommendation(row['effective_stock'], row['avg_sales'],
                                row['horizon_days'] + extra_days, row['pack_size'],
                                row['days_to_expiry'], row['velocity'])


def _group_sum(rows, extra_days):
    """Сумма рекомендаций группы на горизонте +extra_days, рублей (позиции без цены — 0)."""
    total = 0.0
    for row in rows:
        if row['price'] is None:
            continue
        total += row['price'] * _recommend_at(row, extra_days)
    return round(total, 2)


def _min_order_state(rows, params, other_bars_sum=0.0, apply_fill=True,
                     max_extra_days=MIN_ORDER_MAX_EXTRA_DAYS):
    """Добор группы поставщика до минимального заказа: на сколько дней растянуть горизонт.

    Поставщик не принимает заказ дешевле min_order_sum (docs/suppliers.md), поэтому
    «заказать три пиццы» невозможно физически. Вместо отдельной логики «добить чем
    попало» группа считается на один увеличенный горизонт: заказываем тот же товар,
    что и так уходит, но реже и крупнее. Доля каждой позиции остаётся пропорциональной
    её расходу, формула строки не меняется — меняется только число дней.

        base_sum = Σ price × recommended(0)                     — что нужно на самом деле
        need     = min_order_sum − (уже в черновике по другим барам, если минимум на заказ)
        extra    = наименьшее 1..max_extra_days, при котором Σ price × recommended(extra) >= need

    Сумма растёт вместе с extra (цель = расход × (горизонт + запас) не убывает), поэтому
    первое подходящее extra — минимальное: система не заказывает больше, чем нужно для
    минимума. Добор не применяется, если:
        - минимум не задан (0) или уже набран;
        - в группе нечего заказывать (все рекомендации нулевые) — заказ сегодня не нужен;
        - минимум не набирается и за max_extra_days: рекомендации остаются базовыми,
          reachable = False, и управляющий решает сам (добавить позиции, заказать позже,
          договориться с поставщиком).

    Возвращает dict для ответа доски; extra_days = 0 означает «считаем как обычно».
    """
    min_sum = int(params.get('min_order_sum') or 0)
    scope = params.get('min_order_scope') or 'bar'
    base_sum = _group_sum(rows, 0)
    state = {
        'min_order_sum': min_sum,
        'min_order_scope': scope,
        'base_sum': base_sum,
        'sum': base_sum,
        'extra_days': 0,
        'reachable': True,
        'other_bars_sum': round(other_bars_sum, 2),
        'no_price_count': sum(1 for r in rows if r['price'] is None),
        'priced_count': sum(1 for r in rows if r['price'] is not None),
        'max_extra_days': max_extra_days,
        'applies': bool(apply_fill),
        'need_sum': float(min_sum),      # сколько нужно набрать этому бару (уточняется ниже)
    }
    # «Общая» — это не доставка: минимум считается по бару, поэтому там добора нет.
    if not apply_fill or min_sum <= 0 or not any(r['recommended_base'] > 0 for r in rows):
        return state
    need = min_sum - (other_bars_sum if scope == 'order' else 0.0)
    state['need_sum'] = round(max(0.0, need), 2)
    if base_sum >= need:
        return state
    for extra in range(1, max_extra_days + 1):
        total = _group_sum(rows, extra)
        if total >= need:
            state['extra_days'] = extra
            state['sum'] = total
            return state
    state['reachable'] = False
    state['max_sum'] = _group_sum(rows, max_extra_days)
    return state


def _urgency_level(stock, avg_sales, days_to_delivery, velocity):
    """Уровень срочности позиции.

    days_to_delivery — календарных дней до ближайшей поставки, если заказать
    сегодня (по календарю поставщика; раньше здесь был lead_time_days).

    critical: stock < −STOCK_ZERO_EPS (учётная ошибка) — независимо от скорости продаж
    low:      velocity in ('dead', 'slow') — редко продаётся, не критично
    critical: days_left < 1
    high:     days_left < days_to_delivery (поставка не успеет)
    medium:   days_left < days_to_delivery + SAFETY_DAYS
    low:      остальное
    """
    if stock < -STOCK_ZERO_EPS:
        return 'critical'
    if velocity in ('dead', 'slow'):
        return 'low'
    if avg_sales <= 0:
        return 'low'
    days_left = stock / avg_sales
    if days_left < 1:
        return 'critical'
    if days_left < days_to_delivery:
        return 'high'
    if days_left < days_to_delivery + SAFETY_DAYS:
        return 'medium'
    return 'low'


def _delivery_plan(today, params):
    """(ближайшая поставка, следующая за ней, дней до ближайшей, дней до следующей).

    По сроку и дням доставки поставщика из справочника. «Дней до следующей» —
    горизонт, который должен покрыть заказ (см. _calc_recommendation).
    """
    weekdays = params.get('delivery_weekdays')
    first = next_delivery_date(today, params['lead_time_days'], weekdays)
    following = delivery_after(first, weekdays)
    return first, following, (first - today).days, (following - today).days


def _fmt_num(value):
    """Число для фразы: целое без «.0», иначе до двух знаков без хвостовых нулей."""
    value = float(value)
    if abs(value - round(value)) < 0.005:
        return str(int(round(value)))
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def _fmt_day(value):
    """'2026-09-14' → 'пн 14.09' для фразы-причины."""
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')[d.weekday()]} {d.strftime('%d.%m')}"


def _fmt_money(value):
    """Рубли без копеек, разряды через пробел: 10240.4 → «10 240 руб.»."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return str(value)
    return f'{n:,}'.replace(',', ' ') + ' руб.'


def _kegs_label(liters, keg_liters):
    """«1 кега по 30 л» / «3 кеги по 20 л» — сколько бочек в рекомендации."""
    if not keg_liters or keg_liters <= 0:
        return ''
    kegs = int(round(liters / keg_liters))
    if kegs <= 0:
        return ''
    tail = kegs % 10
    if kegs % 100 in (11, 12, 13, 14) or tail == 0 or tail >= 5:
        word = 'кег'
    elif tail == 1:
        word = 'кега'
    else:
        word = 'кеги'
    return f'{kegs} {word} по {_fmt_num(keg_liters)} л'


def _reason(calc, window_days):
    """Фраза-причина и код: одно объяснение = одно действие (S-14, S-15).

    calc — неокруглённые величины расчёта (stock, on_order, avg, target, recommended,
    horizon_days, first_delivery, next_delivery, pack_size, velocity, days_left,
    days_to_expiry, nearest_expiry, is_new, days_in_period, unit, is_negative).
    Порядок проверок повторяет расчёт рекомендации, чтобы фраза никогда не
    расходилась с числом; все числа в фразе — те же, что в формуле, до двух
    знаков, чтобы «нужно − есть − в пути = заказать» сходилось на калькуляторе:
        out_of_rotation позиции нет в остатках iiko и расхода давно не было — сорт ушёл
        negative_stock  остаток < −STOCK_ZERO_EPS и заказывать нечего — проверить учёт
        near_expiry     партия истекает < NEAR_EXPIRY_BLOCK_DAYS — не заказываем
        no_movement     расхода нет (velocity dead)
        slow            редко расходится (velocity slow, только штучные) — не пополняем
        order           рекомендация > 0: до поставки X нужно N (avg × дней), есть, в пути
        min_order       то же, но горизонт растянут ради минимального заказа поставщика
        in_transit      рекомендация 0, но есть «в пути»
        enough          хватает до следующей поставки
    """
    unit = calc['unit']
    stock, on_order = calc['stock'], calc['on_order']
    shelf = calc.get('shelf', stock)
    d = calc['days_to_expiry']
    if calc.get('blocked'):
        last_out = calc.get('last_out')
        when = f'последний расход {_fmt_day(last_out)}' if last_out else 'расхода за период нет'
        return 'out_of_rotation', (f'нет в остатках iiko, {when}: сорт вышел из ротации, '
                                   f'если вернулся — впишите количество руками')
    # Минус в остатке: товара на полке нет (решение владельца 2026-09-19). Если
    # заказывать нечего (нет расхода, редкий, истекает срок) — говорим только про учёт.
    negative_note = (f'остаток {_fmt_num(stock)} {unit}: проверьте учёт в iiko'
                     if calc['is_negative'] else '')
    if negative_note and calc['recommended'] <= 0:
        if d is not None and 0 <= d < NEAR_EXPIRY_BLOCK_DAYS:
            tail = f', партия истекает {_fmt_day(calc["nearest_expiry"])} — заказ не нужен'
        elif calc['velocity'] == 'dead':
            tail = f', расхода за {window_days} дн. нет — заказывать нечего'
        elif calc['velocity'] == 'slow':
            tail = ', расходится редко — не пополняем автоматически'
        elif on_order > 0:
            tail = f', в пути {_fmt_num(on_order)} {unit} — хватит до поставки'
        else:
            tail = ''
        return 'negative_stock', negative_note + tail
    if d is not None and 0 <= d < NEAR_EXPIRY_BLOCK_DAYS:
        return 'near_expiry', f'партия истекает {_fmt_day(calc["nearest_expiry"])} ({d} дн.): не заказываем, продаём что есть'
    if calc['velocity'] == 'dead':
        if calc['is_new']:
            return 'no_movement', f'нет расхода с прихода ({calc["days_in_period"]} дн.)'
        return 'no_movement', f'без движения {window_days} дн.'
    if calc['velocity'] == 'slow':
        return 'slow', f'редко расходится ({_fmt_num(calc["avg"] * DAYS_PER_WEEK)} в нед.): не пополняем автоматически'
    cover = calc['horizon_days'] + SAFETY_DAYS
    if calc['recommended'] > 0:
        extra = calc.get('min_order_extra_days') or 0
        if extra:
            # Минимум поставщика не набирается тем, что нужно к ближайшей поставке:
            # берём тот же товар на больший срок (заказ реже, но крупнее).
            text = (f'до минимального заказа {_fmt_money(calc.get("min_order_sum"))} берём запас на'
                    f' {cover + extra} дн. вместо {cover}: нужно {_fmt_num(calc["target"])} {unit}'
                    f' ({_fmt_num(calc["avg"])} в день), есть {_fmt_num(stock)}')
        else:
            text = (f'до поставки {_fmt_day(calc["next_delivery"])} нужно {_fmt_num(calc["target"])} {unit}'
                    f' ({_fmt_num(calc["avg"])} в день × {cover} дн. с запасом), есть {_fmt_num(shelf)}')
        if negative_note:
            text = f'{negative_note}, полка пустая — ' + text
        if on_order > 0:
            text += f', в пути {_fmt_num(on_order)}'
        text += f': заказать {_fmt_num(calc["recommended"])} к {_fmt_day(calc["first_delivery"])}'
        kegs = _kegs_label(calc['recommended'], calc.get('keg_liters'))
        if kegs:
            text += f' ({kegs})'
        elif calc['pack_size'] > 1:
            text += f' (упаковка {_fmt_num(calc["pack_size"])})'
        return ('min_order' if extra else 'order'), text
    if on_order > 0:
        return 'in_transit', f'в пути {_fmt_num(on_order)} {unit}: с ним хватит до поставки {_fmt_day(calc["next_delivery"])}'
    if calc['days_left'] is not None:
        return 'enough', f'хватит на {_fmt_num(calc["days_left"])} дн., следующая поставка {_fmt_day(calc["next_delivery"])} через {calc["horizon_days"]} дн.'
    return 'enough', 'расхода нет'


stocks_bp = Blueprint('stocks', __name__)


# ---------------------------------------------------------------------------
# Общие помощники эндпоинтов остатков (с 2026-09-10, этап 0 редизайна /stocks)
# ---------------------------------------------------------------------------

# Верхние группы номенклатуры iiko (Product.TopParent) — тот же источник, что у дашборда.
TOP_PARENT_BOTTLES = DashboardMetrics.TOP_PARENT_BOTTLES   # «Напитки Фасовка»
TOP_PARENT_DRAFT = DashboardMetrics.TOP_PARENT_DRAFT       # «Напитки Розлив»
TOP_PARENT_KITCHEN = DashboardMetrics.TOP_PARENT_KITCHEN   # «ЕДА» (решение владельца 2026-09-10)
# GUID группы «Напитки Фасовка» — на случай номенклатуры, где parentId ещё GUID, а не имя.
FASOVKA_GROUP_ID = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'

# Уровень остатка по дням (Фасовка / Кухня / Сроки годности): days_left = stock / avg_per_day.
STOCK_LEVEL_LOW_DAYS = 3      # меньше — «Низкий»
STOCK_LEVEL_MEDIUM_DAYS = 7   # меньше — «Средний», иначе «Высокий»
# Уровень остатка таплиста по литрам: кеги 20/30/50 л, <10 л — на исходе, <25 л — меньше кеги.
TAPLIST_LOW_LITERS = 10
TAPLIST_MEDIUM_LITERS = 25

_IIKO_UNAVAILABLE_MSG = ('iiko не отдал остатки или операции по складам. '
                         'Данные не показаны, чтобы не выдать нули за факт.')


class UnknownBarError(ValueError):
    """Имя бара не из BARS и не «Общая»."""


def _resolve_bar(bar):
    """(target_store_id, target_kpp) для имени бара; «Общая» → (None, None)."""
    if bar == 'Общая':
        return None, None
    bar_id = _BAR_ID_MAP.get(bar)
    if not bar_id:
        raise UnknownBarError(bar)
    return _STORE_ID_MAP.get(bar_id), _BAR_KPP_MAP.get(bar_id)


def _bar_from_request():
    """Разобрать ?bar= → (bar, target_store_id, target_kpp, error_response)."""
    bar = request.args.get('bar', '')
    if not bar:
        return None, None, None, (jsonify({'error': 'Требуется параметр bar'}), 400)
    try:
        store_id, kpp = _resolve_bar(bar)
    except UnknownBarError:
        return None, None, None, (jsonify({
            'error': f'Неизвестный бар: {bar}',
            'known_bars': list(BARS) + ['Общая'],
        }), 400)
    return bar, store_id, kpp, None


def _load_stock_data():
    """Снимок сети + номенклатура → (snapshot, nomenclature, error_response).

    Сбой iiko — явная ошибка 503 с кодом, а не пустой список (S-08). Именно 503:
    фронт повторяет только 502 (прокси при пробуждении), а это ответ приложения.
    """
    snapshot = get_stock_snapshot()
    if not snapshot:
        return None, None, (jsonify({'error': _IIKO_UNAVAILABLE_MSG, 'code': 'iiko_unavailable'}), 503)
    if not snapshot.get('balances'):
        return None, None, (jsonify({'error': 'iiko вернул пустые остатки по складам',
                                     'code': 'empty_balances'}), 503)
    nomenclature = get_stocks_nomenclature()
    if not nomenclature:
        return None, None, (jsonify({'error': 'Не удалось получить номенклатуру товаров',
                                     'code': 'nomenclature_unavailable'}), 503)
    return snapshot, nomenclature, None


def _snapshot_today(snapshot):
    return date.fromisoformat(snapshot['today'])


def _bar_store_map():
    """{имя бара: store_id} для сверки заказов с приходами iiko (без «Общая»)."""
    return {name: _STORE_ID_MAP[bid] for name, bid in _BAR_ID_MAP.items() if bid}


def _draft_sum(draft_items, only_bar=None, exclude_bar=None):
    """Сумма черновика поставщика в рублях по сохранённым ценам позиций.

    draft_items — [{product_id, bar, qty, price}] из core.order_store.open_state.
    Позиция без цены в сумму не входит (её видно как «N поз. без цены»).
    only_bar — считать один бар, exclude_bar — все бары, кроме этого
    (что коллеги уже набрали в другие бары одного заказа поставщику).
    """
    total = 0.0
    for it in draft_items or []:
        if only_bar is not None and it.get('bar') != only_bar:
            continue
        if exclude_bar is not None and it.get('bar') == exclude_bar:
            continue
        if it.get('price') is None:
            continue
        total += float(it['price']) * float(it.get('qty') or 0)
    return round(total, 2)


def _orders_context(snapshot, bar, target_store_id):
    """Заказы поставщикам для доски: сверка с приходами и количества «в пути»/в черновике.

    Возвращает (on_order, open_orders, draft_qty, draft_items, error):
        on_order     — сумма по открытым заказам (sent/received, ещё не оприходовано)
                       по складу бара; для «Общая» — по всей сети;
        open_orders  — список открытых заказов по позиции (для подсказки в UI);
        draft_qty    — {product_id: qty} в общем черновике для этого бара
                       (для «Общая» — сумма по барам, только для показа);
        draft_items  — {supplier: [{product_id, bar, qty, price}]} по всем барам:
                       минимальный заказ поставщика может считаться на весь заказ;
        error        — None или текст: файл заказов недоступен. Доска в этом случае
                       всё равно отдаётся (нули), но с флагом orders_available = false,
                       чтобы фронт не предлагал «Взять» то, что уже может быть в пути.
    Три количества берутся из одного чтения файла (open_state), чтобы ответ не
    смешивал две версии файла при правке коллеги в этот же момент.
    """
    try:
        store = get_order_store()
        store.reconcile_with_operations(snapshot.get('operations') or [], _bar_store_map())
        scope_bar = bar if target_store_id else None
        on_order, open_orders, drafts, draft_items = store.open_state(scope_bar)
        return on_order, open_orders, drafts, draft_items, None
    except Exception as e:  # noqa: BLE001 — доска важнее сверки заказов, но молчать нельзя
        print(f"[ORDERS] orders context unavailable: {e}")
        return {}, {}, {}, {}, str(e)


def _fasovka_ids(nomenclature):
    """Товары верхней группы «Напитки Фасовка» (по имени группы или её GUID)."""
    return {pid for pid, info in nomenclature.items()
            if info.get('parentId') in (TOP_PARENT_BOTTLES, FASOVKA_GROUP_ID)}


# Типы номенклатуры, у которых бывают складские остатки; блюда (DISH) и
# модификаторы (MODIFIER, соусы «порц») остатков не имеют и в заказ не идут.
STOCK_PRODUCT_TYPES = ('GOODS', 'PREPARED')


def _classify(product_id, info, fasovka_ids):
    """'bottle' | 'draft' | 'kitchen' | None по верхней группе номенклатуры.

    Кухня = группа «ЕДА», а не белый список поставщиков и не единица измерения
    (масло в литрах — кухня). Кега = группа «Напитки Розлив» в литрах; банка в
    штуках под «Розлив» — не кега и не фасовка, пропускается. Товар без
    известной верхней группы (сирота в XML, старый кэш с GUID) считается кегой,
    только если это GOODS в литрах — прежнее правило таплиста как запасной вариант.
    """
    if not info or info.get('type') not in STOCK_PRODUCT_TYPES:
        return None
    parent = info.get('parentId')
    unit = info.get('mainUnit')
    if product_id in fasovka_ids or parent == TOP_PARENT_BOTTLES:
        return 'bottle'
    if parent == TOP_PARENT_KITCHEN:
        return 'kitchen'
    if parent == TOP_PARENT_DRAFT:
        return 'draft' if unit == 'л' else None
    if parent not in (TOP_PARENT_BOTTLES, TOP_PARENT_KITCHEN, TOP_PARENT_DRAFT) \
            and info.get('type') == 'GOODS' and unit == 'л':
        return 'draft'
    return None


def _stock_level_by_days(stock, avg_per_day):
    """'low' | 'medium' | 'high' по дням хватания; без расхода — 'high'."""
    if avg_per_day <= 0:
        return 'high'
    days_left = stock / avg_per_day
    if days_left < STOCK_LEVEL_LOW_DAYS:
        return 'low'
    if days_left < STOCK_LEVEL_MEDIUM_DAYS:
        return 'medium'
    return 'high'


def _collect_stock(balances, nomenclature, target_store_id, fasovka_ids, kinds):
    """Остатки нужных видов по складу бара (или всей сети при target_store_id=None).

    → {product_id: {name, category, unit, kind, stock}}; stock — сумма amount по
    записям balance/stores (для «Общая» — по всем складам).
    """
    products = {}
    for balance in balances:
        product_id = balance.get('product')
        if not product_id:
            continue
        if target_store_id and balance.get('store') != target_store_id:
            continue
        info = nomenclature.get(product_id)
        kind = _classify(product_id, info, fasovka_ids)
        if kind not in kinds:
            continue
        entry = products.get(product_id)
        if entry is None:
            entry = {
                'name': info.get('name') or product_id,
                'category': info.get('category') or 'Без поставщика',
                'unit': info.get('mainUnit') or 'шт',
                'kind': kind,
                'stock': 0.0,
            }
            products[product_id] = entry
        try:
            entry['stock'] += float(balance.get('amount', 0) or 0)
        except (TypeError, ValueError):
            pass
    return products


def _products_from_operations(operations, nomenclature, target_store_id, fasovka_ids, kinds,
                             known_ids):
    """Товары без строки остатка, но с движением по складу за окно → {product_id: {...}}.

    Зачем. Доска строилась только по `balance/stores`, а iiko не присылает строку
    для товара, которого на складе нет. Позиция, кончившаяся вчера, исчезала с
    экрана заказа ровно тогда, когда её надо заказывать (замечание владельца
    2026-09-19). Такие товары добавляются с остатком 0 и пометкой `no_stock_row`.

    Считаются только операции нужного склада (для «Общей» — все, кроме
    перемещений внутри сети, как в core/stock_consumption). Классификация и
    единицы — те же, что у остатков; товара нет в номенклатуре — пропускаем.
    """
    products = {}
    for record in operations:
        product_id = record.get('product')
        if not product_id or product_id in known_ids or product_id in products:
            continue
        if target_store_id and record.get('primaryStore') != target_store_id:
            continue
        if not target_store_id and record.get('documentType') == INTERNAL_TRANSFER_TYPE:
            continue
        info = nomenclature.get(product_id)
        kind = _classify(product_id, info, fasovka_ids)
        if kind not in kinds:
            continue
        products[product_id] = {
            'name': info.get('name') or product_id,
            'category': info.get('category') or 'Без поставщика',
            'unit': info.get('mainUnit') or 'шт',
            'kind': kind,
            'stock': 0.0,
            'no_stock_row': True,
        }
    return products


def _normalize_keg_name(name):
    """Название кеги без префикса «Кег», объёма и хвоста — общее для кранов и iiko."""
    base = name or ''
    base = re.sub(r'^Кег\s+', '', base, flags=re.IGNORECASE)
    base = re.sub(r',?\s*\d+\s*л.*', '', base)
    base = re.sub(r'\s+л\s*$', '', base)
    base = re.sub(r',?\s*кег.*', '', base, flags=re.IGNORECASE)
    base = re.sub(r',\s*$', '', base)
    return base.strip()


def _load_chz_by_gtin():
    """Кэш ЧЗ → ({gtin14: item}, chz_updated_at | None). Нет файла — пусто, без ошибки."""
    chz_by_gtin = {}
    chz_updated_at = None
    try:
        chz_mtime = os.path.getmtime(str(_CHZ_CACHE_FILE))
        chz_updated_at = datetime.fromtimestamp(chz_mtime).isoformat()
        with open(_CHZ_CACHE_FILE, encoding='utf-8') as f:
            chz_items = json.load(f)
        for item in chz_items:
            gtin = str(item.get('gtin', '')).zfill(14)
            chz_by_gtin[gtin] = item
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"[STOCKS] CHZ cache unavailable: {e}")
    return chz_by_gtin, chz_updated_at


def _chz_batches(chz_item, target_kpp):
    """(count, batches) по КПП бара; при target_kpp=None — все партии юрлица."""
    if target_kpp:
        count = 0
        batches = []
        for slot in chz_item.get('by_kpp', []):
            if slot.get('kpp') == target_kpp:
                count += slot.get('count', 0)
                batches.extend(slot.get('batches', []))
        return count, batches
    return chz_item.get('count', 0), list(chz_item.get('batches', []))


def _nearest_expiry(expiration_dates, today):
    """(nearest_expiry, days_to_expiry): ближайшая будущая дата, иначе самая поздняя.

    Если все партии просрочены, возвращается последняя просроченная дата и
    отрицательное число дней — потребитель решает, что с этим делать.
    """
    if not expiration_dates:
        return None, None
    future = [d for d in expiration_dates if d >= today.isoformat()]
    nearest = future[0] if future else expiration_dates[-1]
    try:
        exp = datetime.strptime(nearest, "%Y-%m-%d").date()
        return nearest, (exp - today).days
    except ValueError:
        return nearest, None


def _stock_items_response(bar, snapshot, target_store_id, items, low_stock_count, extra=None):
    payload = {
        'bar': bar,
        'updated_at': snapshot['fetched_at'],
        'consumption_scope': 'store' if target_store_id else 'network',
        'window_days': snapshot['window_days'],
        'total_items': len(items),
        'low_stock_count': low_stock_count,
        'items': items,
    }
    if extra:
        payload.update(extra)
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------

@stocks_bp.route('/api/stocks/taplist', methods=['GET'])
def get_taplist_stocks():
    """Остатки кег из iiko в литрах — только сорта, стоящие на кранах бара.

    Краны — из taps_manager (status == active), остатки — из снимка сети
    balance/stores по складу бара. Сопоставление по нормализованному названию
    (см. _normalize_keg_name), только точное совпадение.
    """
    try:
        bar, target_store_id, _, err = _bar_from_request()
        if err:
            return err

        # Активные краны по складам: фильтр «только то, что на кранах» действует
        # для каждого склада отдельно, поэтому в режиме «Общая» кеги бара без
        # кранов не прячутся за кранами соседнего бара.
        active_by_store = {}
        beer_to_taps = {}
        bar_ids = list(_STORE_ID_MAP.keys()) if bar == 'Общая' else [_BAR_ID_MAP[bar]]
        for bar_id in bar_ids:
            names = set()
            result = taps_manager.get_bar_taps(bar_id)
            for tap in result.get('taps', []):
                if tap.get('status') == 'active' and tap.get('current_beer'):
                    beer_name = _normalize_keg_name(tap['current_beer'])
                    names.add(beer_name)
                    beer_to_taps.setdefault(beer_name, []).append(tap.get('tap_number', '?'))
            active_by_store[_STORE_ID_MAP.get(bar_id)] = names
        active_beers = set().union(*active_by_store.values()) if active_by_store else set()

        snapshot, nomenclature, err = _load_stock_data()
        if err:
            return err

        beer_stocks = {}
        for balance in snapshot['balances']:
            product_id = balance.get('product')
            if target_store_id and balance.get('store') != target_store_id:
                continue
            info = nomenclature.get(product_id)
            if not info or info.get('type') != 'GOODS' or info.get('mainUnit') != 'л':
                continue
            if info.get('parentId') == TOP_PARENT_KITCHEN:
                continue  # масло и прочее кухонное в литрах — не кеги
            base_name = _normalize_keg_name(info.get('name') or product_id)
            store_active = active_by_store.get(balance.get('store'))
            if store_active and base_name not in store_active:
                continue
            entry = beer_stocks.setdefault(base_name, {
                'remaining_liters': 0.0,
                'category': info.get('category') or 'Разливное',
                'on_tap': base_name in active_beers,
            })
            try:
                entry['remaining_liters'] += float(balance.get('amount', 0) or 0)
            except (TypeError, ValueError):
                pass

        for active_beer in active_beers:
            beer_stocks.setdefault(active_beer, {
                'remaining_liters': 0.0, 'category': 'Разливное', 'on_tap': True,
            })

        taps_data = []
        total_liters = 0.0
        low_stock_count = 0
        negative_stock_count = 0
        for beer_name, beer_data in beer_stocks.items():
            remaining = beer_data['remaining_liters']
            if remaining == 0 and not beer_data['on_tap']:
                continue
            total_liters += remaining if remaining > 0 else 0
            if remaining < 0:
                stock_level = 'negative'
                negative_stock_count += 1
                low_stock_count += 1
            elif remaining < TAPLIST_LOW_LITERS:
                stock_level = 'low'
                low_stock_count += 1
            elif remaining < TAPLIST_MEDIUM_LITERS:
                stock_level = 'medium'
            else:
                stock_level = 'high'
            tap_numbers = beer_to_taps.get(beer_name, [])
            taps_data.append({
                'beer_name': beer_name,
                'category': beer_data['category'],
                'remaining_liters': round(remaining, 1),
                'stock_level': stock_level,
                'on_tap': beer_data['on_tap'],
                'tap_numbers': ', '.join(map(str, sorted(tap_numbers))) if tap_numbers else '—',
                'taps_count': len(tap_numbers),
            })
        taps_data.sort(key=lambda x: x['remaining_liters'])

        return jsonify({
            'bar': bar,
            'updated_at': snapshot['fetched_at'],
            'total_items': len(taps_data),
            'total_liters': round(total_liters, 1),
            'low_stock_count': low_stock_count,
            'negative_stock_count': negative_stock_count,
            'active_taps_count': len(active_beers),
            'taps': taps_data,
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/taplist: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _stock_tab_items(snapshot, nomenclature, target_store_id, kinds):
    """Общая сборка для вкладок Фасовка и Кухня: остаток + расход по складу бара.

    Позиции с остатком, но без операций за окно, остаются в списке
    (avg_sales = 0, «Высокий»), а не исчезают.
    """
    fasovka_ids = _fasovka_ids(nomenclature)
    products = _collect_stock(snapshot['balances'], nomenclature, target_store_id, fasovka_ids, kinds)
    stats = aggregate_consumption(snapshot['operations'], products.keys(),
                                  target_store_id, _snapshot_today(snapshot),
                                  snapshot['window_days'],
                                  stock_now={pid: p['stock'] for pid, p in products.items()})
    directory = get_supplier_directory().view()
    # Цена нужна и здесь: позиция, добавленная в заказ из «Фасовки» или «Меню кухни»,
    # должна попадать в сумму заказа наравне с позицией доски (docs/orders.md).
    prices = resolve_prices(snapshot['operations'], snapshot['balances'], products.keys())
    items = []
    for product_id, data in products.items():
        st = stats[product_id]
        price_info = prices.get(product_id) or {}
        items.append({
            'product_id': product_id,
            'category': data['category'],
            'supplier': directory.resolve(data['category']),   # каноническое имя из справочника
            'name': data['name'],
            'unit': data['unit'],
            'price': price_info.get('price'),
            'price_source': price_info.get('source'),
            'stock': round(data['stock'], 1),
            'avg_sales': round(st['avg_per_day'], 2),
            'days_in_period': st['days_in_period'],
            'is_new': st['is_new'],
            'stock_level': _stock_level_by_days(data['stock'], st['avg_per_day']),
        })
    items.sort(key=lambda x: (x['category'], x['name']))
    return items


@stocks_bp.route('/api/stocks/kitchen', methods=['GET'])
def get_kitchen_stocks():
    """Остатки кухни (верхняя группа «ЕДА») и расход за окно по складу бара."""
    try:
        bar, target_store_id, _, err = _bar_from_request()
        if err:
            return err
        snapshot, nomenclature, err = _load_stock_data()
        if err:
            return err
        items = _stock_tab_items(snapshot, nomenclature, target_store_id, {'kitchen'})
        low = sum(1 for it in items if it['stock_level'] == 'low')
        return _stock_items_response(bar, snapshot, target_store_id, items, low)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/kitchen: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@stocks_bp.route('/api/stocks/bottles', methods=['GET'])
def get_bottles_stocks():
    """Остатки фасовки (верхняя группа «Напитки Фасовка») и расход по складу бара."""
    try:
        bar, target_store_id, _, err = _bar_from_request()
        if err:
            return err
        snapshot, nomenclature, err = _load_stock_data()
        if err:
            return err
        items = _stock_tab_items(snapshot, nomenclature, target_store_id, {'bottle'})
        low = sum(1 for it in items if it['stock_level'] == 'low')
        return _stock_items_response(bar, snapshot, target_store_id, items, low)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/bottles: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@stocks_bp.route('/api/stocks/chz', methods=['GET'])
def get_chz_stocks():
    """Остатки фасованного пива из Честный ЗНАК.

    Возвращает: название - количество - срок годности
    Данные получаются через ЧЗ API (cises/search + product/info).
    Работает только на бар-ПК с установленным CryptoPro CSP и Рутокеном.
    """
    try:
        chz_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chz_test')
        if chz_path not in sys.path:
            sys.path.insert(0, chz_path)

        from chz import get_chz_stock

        stock = get_chz_stock()

        # Подсчёт кодов близких к окончанию срока (< 30 дней)
        today = datetime.now().date()
        near_expiry_codes = 0
        for item in stock:
            has_near_expiry = False
            for exp_str in item.get("expiration_dates", []):
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    if 0 <= (exp_date - today).days < NEAR_EXPIRY_WARN_DAYS:
                        has_near_expiry = True
                        break
                except ValueError:
                    pass
            if has_near_expiry:
                near_expiry_codes += item.get('count', 0)

        return jsonify({
            'total_items': len(stock),
            'total_codes': sum(s['count'] for s in stock),
            'near_expiry_codes': near_expiry_codes,
            'items': stock
        })

    except ImportError:
        return jsonify({'error': 'ЧЗ модуль недоступен. Требуется бар-ПК с CryptoPro CSP.'}), 503
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/chz: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@stocks_bp.route('/api/chz/stock', methods=['GET'])
def get_chz_stock_api():
    """Остатки ЧЗ с датами годности. Читает из кеша chz_stock.json."""
    try:
        mtime = os.path.getmtime(str(_CHZ_CACHE_FILE))
        updated_at = datetime.fromtimestamp(mtime).isoformat()
        with open(_CHZ_CACHE_FILE, encoding='utf-8') as f:
            items = json.load(f)
    except FileNotFoundError:
        return jsonify({'items': [], 'updated_at': None, 'error': 'no data'}), 404
    except (json.JSONDecodeError, OSError):
        return jsonify({'items': [], 'updated_at': None, 'error': 'cache corrupted or updating'}), 500

    return jsonify({'items': items, 'updated_at': updated_at})


def start_chz_refresh() -> tuple[dict, int]:
    """Запустить фоновое обновление кеша ЧЗ через /cises/search. Общая логика.

    Делает на бар-ПК: token refresh → chz.py search-stock (beer+nabeer+softdrinks
    через синхронный /cises/search, привязка к бару по modId) → pull chz_stock.json.
    Возвращает сразу ('started'); прогресс — в chz_test/debug/refresh.log.

    ВАЖНО: зовётся из ДВУХ мест — HTTP-эндпоинта (кнопка в UI) и планировщика
    (core/chz_scheduler.py) НАПРЯМУЮ. Планировщик обязан звать эту функцию, а не
    POST'ить на /api/chz/refresh: у него нет сессии, и auth-гейт отбивает внутренний
    запрос 401 — из-за этого авторефреш молча стоял (см. docs/lessons.md).

    Возвращает (result, http_status): result['status'] ∈
    {'started', 'already_running', 'error'}.

    Контекст: с 2026-06 коды выводятся из оборота сразу при приёмке
    (RETIRED/OWN_USE), фильтр INTRODUCED пуст, а dispenser-выгрузка по RETIRED
    виснет — поэтому остатки тянем синхронным /cises/search. См. docs/expiration.md.
    """
    global _refresh_proc, _refresh_log_file
    if not os.environ.get('REMOTE_PASS'):
        return {'status': 'error', 'error': 'REMOTE_PASS not configured'}, 503
    with _refresh_lock:
        # Cross-worker check: если lock-файл существует и pid в нём жив — refresh уже идёт
        # в другом воркере (или в этом). Lock-файл создаётся atomic'но через O_EXCL.
        if _refresh_proc is not None:
            if _refresh_proc.poll() is None:
                return {'status': 'already_running'}, 409
            _refresh_proc = None
            if _refresh_log_file is not None:
                _refresh_log_file.close()
                _refresh_log_file = None
        # Попытка взять file-lock (atomic). Если уже взят — есть шанс что worker'у-владельцу
        # дали умереть (stale lock). Проверяем mtime: если файл старше 30 минут — снимаем.
        os.makedirs(_CHZ_REFRESH_LOCK.parent, exist_ok=True)
        try:
            if _CHZ_REFRESH_LOCK.exists():
                age = time.time() - _CHZ_REFRESH_LOCK.stat().st_mtime
                if age > 1800:  # 30 минут — refresh всегда укладывается
                    _CHZ_REFRESH_LOCK.unlink()
                else:
                    return {'status': 'already_running', 'note': 'cross-worker lock'}, 409
            fd = os.open(str(_CHZ_REFRESH_LOCK),
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, f'{os.getpid()}\n'.encode())
            os.close(fd)
        except FileExistsError:
            return {'status': 'already_running', 'note': 'cross-worker lock race'}, 409
        except OSError as e:
            return {'status': 'error', 'error': f'lock failed: {e}'}, 500

        remote_exec = str(_BASE_DIR / 'remote_exec.py')
        log_file = None
        try:
            # Truncate log so each refresh starts fresh
            log_file = open(_CHZ_REFRESH_LOG, 'w', encoding='utf-8')
            log_file.write(f'=== refresh started {datetime.now().isoformat()} ===\n')
            log_file.flush()
            _refresh_proc = subprocess.Popen(
                [sys.executable, remote_exec, 'run', 'search-stock'],
                stdout=log_file,
                stderr=log_file
            )
            _refresh_log_file = log_file
        except OSError as e:
            if log_file is not None:
                log_file.close()
            # Снять lock — refresh не стартовал
            try:
                _CHZ_REFRESH_LOCK.unlink()
            except OSError:
                pass
            return {'status': 'error', 'error': str(e)}, 500
    return {'status': 'started'}, 200


@stocks_bp.route('/api/chz/refresh', methods=['POST'])
def refresh_chz_stock():
    """HTTP-обёртка над start_chz_refresh() (кнопка «Обновить ЧЗ» в UI).

    Тело вынесено в start_chz_refresh(), чтобы планировщик мог звать ту же логику
    напрямую, минуя auth-гейт. Здесь только перевод результата в JSON-ответ.
    """
    result, code = start_chz_refresh()
    return jsonify(result), code


@stocks_bp.route('/api/chz/refresh/status', methods=['GET'])
def refresh_chz_status():
    """Статус последнего/текущего refresh: running/done/idle + хвост лога."""
    global _refresh_proc
    with _refresh_lock:
        if _refresh_proc is not None:
            poll = _refresh_proc.poll()
            running = poll is None
            exit_code = poll
            # Если процесс завершился — снимаем cross-worker lock, чтобы можно было
            # запустить следующий refresh. Делаем только в worker'е-владельце процесса.
            if not running:
                try:
                    if _CHZ_REFRESH_LOCK.exists():
                        _CHZ_REFRESH_LOCK.unlink()
                except OSError:
                    pass
        else:
            running = False
            exit_code = None
    log_tail = ''
    try:
        if _CHZ_REFRESH_LOG.exists():
            with open(_CHZ_REFRESH_LOG, encoding='utf-8', errors='replace') as f:
                log_tail = f.read()[-3000:]
    except OSError:
        pass
    cache_updated = None
    try:
        cache_updated = datetime.fromtimestamp(_CHZ_CACHE_FILE.stat().st_mtime).isoformat()
    except OSError:
        pass
    return jsonify({
        'running': running,
        'exit_code': exit_code,
        'cache_updated_at': cache_updated,
        'log_tail': log_tail,
    })



@stocks_bp.route('/api/stocks/expiry', methods=['GET'])
def get_bottles_with_expiry():
    """Остатки фасовки из iiko, обогащённые сроками годности из ЧЗ.

    Стыковка iiko↔ЧЗ по barcode (EAN-13) ↔ gtin (GTIN-14, lpad'0').
    Позиции без матча в ЧЗ возвращаются с пустыми expiration_dates.
    Партии — по КПП выбранного бара; для «Общая» — все партии юрлица.
    """
    try:
        bar, target_store_id, target_kpp, err = _bar_from_request()
        if err:
            return err
        snapshot, nomenclature, err = _load_stock_data()
        if err:
            return err

        fasovka_ids = _fasovka_ids(nomenclature)
        products = _collect_stock(snapshot['balances'], nomenclature, target_store_id,
                                  fasovka_ids, {'bottle'})
        today = _snapshot_today(snapshot)
        stats = aggregate_consumption(snapshot['operations'], products.keys(),
                                      target_store_id, today, snapshot['window_days'],
                                      stock_now={pid: p['stock'] for pid, p in products.items()})

        product_to_gtins = invert_to_product_gtins(get_barcode_map())
        chz_by_gtin, chz_updated_at = _load_chz_by_gtin()

        items = []
        matched_count = 0
        near_expiry_count = 0
        for product_id, data in products.items():
            st = stats[product_id]
            matched_gtins = []
            bar_batches = []
            bar_chz_count = 0
            chz_total_count = 0
            for g in product_to_gtins.get(product_id, []):
                chz_item = chz_by_gtin.get(g)
                if not chz_item:
                    continue
                matched_gtins.append(g)
                chz_total_count += chz_item.get('count', 0)
                count, batches = _chz_batches(chz_item, target_kpp)
                bar_chz_count += count
                bar_batches.extend(batches)
            bar_batches.sort(key=lambda b: b.get('production_date', ''), reverse=True)

            expiration_dates = sorted({b['expiration_date'] for b in bar_batches if b.get('expiration_date')})
            production_dates = sorted({b['production_date'] for b in bar_batches if b.get('production_date')})
            has_chz_data = bool(matched_gtins) and bool(bar_batches)
            if has_chz_data:
                matched_count += 1

            nearest_expiry, days_to_expiry = _nearest_expiry(expiration_dates, today)
            latest_expiry = expiration_dates[-1] if expiration_dates else None
            if days_to_expiry is not None and 0 <= days_to_expiry < NEAR_EXPIRY_WARN_DAYS:
                near_expiry_count += 1

            items.append({
                'product_id': product_id,
                'name': data['name'],
                'category': data['category'],
                'unit': data['unit'],
                'stock': round(data['stock'], 1),
                'avg_sales': round(st['avg_per_day'], 2),
                'days_in_period': st['days_in_period'],
                'is_new': st['is_new'],
                'stock_level': _stock_level_by_days(data['stock'], st['avg_per_day']),
                'gtins': matched_gtins,
                'chz_total_count': chz_total_count,
                'bar_chz_count': bar_chz_count,
                'expiration_dates': expiration_dates,
                'production_dates': production_dates,
                'inferred_batches': bar_batches,
                'nearest_expiry': nearest_expiry,
                'latest_expiry': latest_expiry,
                'days_to_expiry': days_to_expiry,
                'has_chz_data': has_chz_data,
            })

        def sort_key(it):
            d = it['days_to_expiry']
            if d is None:
                return (2, 0)
            if d < NEAR_EXPIRY_WARN_DAYS:
                return (0, d)
            return (1, d)

        items.sort(key=sort_key)

        return _stock_items_response(bar, snapshot, target_store_id, items,
                                     sum(1 for it in items if it['stock_level'] == 'low'),
                                     extra={
                                         'chz_updated_at': chz_updated_at,
                                         'matched_items': matched_count,
                                         'near_expiry_count': near_expiry_count,
                                         'near_expiry_warn_days': NEAR_EXPIRY_WARN_DAYS,
                                     })
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/expiry: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@stocks_bp.route('/api/stocks/order-board', methods=['GET'])
def get_order_board():
    """Сводная таблица заказа: фасовка + кеги + кухня в одной таблице.

    Каждая позиция содержит расчёт рекомендованного количества к заказу.
    Ответ сортируется по срочности (critical→high→medium→low), внутри — по days_left.

    Формула рекомендации (см. _calc_recommendation):
        effective    = stock + on_order
        target_stock = avg_sales × (horizon_days + SAFETY_DAYS)
        deficit      = max(0, target_stock − effective)
        recommended  = ceil(deficit / pack_size) × pack_size

        horizon_days — дней до поставки, следующей за ближайшей, по календарю
                       поставщика (справочник /suppliers: срок и дни доставки);
                       заказ должен дожить до следующей возможности получить товар

    Где:
        on_order         — уже заказано и не оприходовано в iiko (открытые
                           заказы core/order_store: «отправлено» и «приехало»);
                           страница не просит второй раз то, что в пути (S-12)
        avg_sales        — расход/день по складу выбранного бара за окно
                           (core/stock_consumption.aggregate_consumption:
                           продажи + перемещения из бара + списания; для
                           новинок делитель — дни с первого прихода)
        lead_time_days   — срок поставки в днях доставки (справочник поставщиков,
                           иначе DEFAULT_LEAD_TIME_DAYS с пометкой supplier_is_default)
        SAFETY_DAYS = 3  — страховой запас на колебания спроса
        pack_size        — минимальная партия (упаковка)

    Минимальный заказ поставщика (min_order_sum в справочнике) считается по группе:
    если сумма рекомендаций (price × recommended по ценам core/purchase_price) меньше
    минимума, горизонт всей группы растягивается на общее число дней, пока сумма не
    дотянет до минимума (_min_order_state). Это заказ реже, но крупнее — тем же товаром,
    который и так расходится; «три пиццы» поставщик с минимумом 10 000 руб. не примет.
    Не набирается за MIN_ORDER_MAX_EXTRA_DAYS — рекомендации остаются базовыми, группа
    помечена reachable = false.

    Если для позиции есть данные ЧЗ и ближайшая партия истекает <14 дней —
    рекомендация принудительно 0 (расходуем то что есть на полке).
    Срочность: см. _urgency_level; считается по effective, но отрицательный
    физический остаток остаётся critical (учётная ошибка не лечится заказом).
    days_left («хватит дн.») — по физическому остатку на полке.
    """
    try:
        bar, target_store_id, target_kpp, err = _bar_from_request()
        if err:
            return err
        snapshot, nomenclature, err = _load_stock_data()
        if err:
            return err

        fasovka_ids = _fasovka_ids(nomenclature)
        kinds = {'bottle', 'draft', 'kitchen'}
        products = _collect_stock(snapshot['balances'], nomenclature, target_store_id,
                                  fasovka_ids, kinds)
        # Позиция, которой нет в остатках iiko, но по которой было движение за окно:
        # кончилась — значит её и надо заказывать (замечание владельца 2026-09-19).
        products.update(_products_from_operations(snapshot['operations'], nomenclature,
                                                  target_store_id, fasovka_ids, kinds,
                                                  set(products)))
        today = _snapshot_today(snapshot)
        stats = aggregate_consumption(snapshot['operations'], products.keys(),
                                      target_store_id, today, snapshot['window_days'],
                                      stock_now={pid: p['stock'] for pid, p in products.items()})

        product_to_gtins = invert_to_product_gtins(get_barcode_map())
        chz_by_gtin, chz_updated_at = _load_chz_by_gtin()
        on_order_map, open_orders_map, draft_map, draft_items_map, orders_error = _orders_context(
            snapshot, bar, target_store_id)
        directory = get_supplier_directory().view()
        # Цена единицы для суммы заказа: последняя приходная накладная, иначе себестоимость
        # остатка (core/purchase_price). Нужна минимальному заказу поставщика в рублях.
        prices = resolve_prices(snapshot['operations'], snapshot['balances'], products.keys())
        plans = {}   # имя поставщика → (first, following, days_to_delivery, horizon_days)
        params_by_supplier = {}

        rows = []
        for product_id, data in products.items():
            stock = data['stock']
            st = stats[product_id]
            avg_sales = st['avg_per_day']
            on_order = float(on_order_map.get(product_id, 0.0))

            nearest_expiry = None
            days_to_expiry = None
            if data['kind'] == 'bottle':
                bar_batches = []
                for g in product_to_gtins.get(product_id, []):
                    chz_item = chz_by_gtin.get(g)
                    if chz_item:
                        bar_batches.extend(_chz_batches(chz_item, target_kpp)[1])
                exp_dates = sorted({b['expiration_date'] for b in bar_batches if b.get('expiration_date')})
                nearest_expiry, days_to_expiry = _nearest_expiry(exp_dates, today)

            params = _supplier_params(data['category'], directory)
            supplier = params['name']
            params_by_supplier.setdefault(supplier, params)
            # Кратность: упаковка поставщика для фасовки и кухни, объём кеги для
            # разливного — целую бочку не разлить на «8 л» (решение владельца 2026-09-19).
            keg_liters, keg_source = (_keg_liters(data['name']) if data['kind'] == 'draft'
                                      else (None, None))
            pack_size = keg_liters if data['kind'] == 'draft' else params['pack_size']
            if supplier not in plans:
                plans[supplier] = _delivery_plan(today, params)
            first_delivery, next_delivery, days_to_delivery, horizon_days = plans[supplier]
            velocity = _velocity(avg_sales, data['unit'])
            # Отрицательный остаток — ошибка учёта, но полка при этом точно пуста:
            # считаем её нулём и заказываем полную цель (решение владельца 2026-09-19).
            # Сам минус остаётся пометкой «проверьте учёт»: недостачу заказом не закрыть.
            is_negative = stock < -STOCK_ZERO_EPS
            shelf_stock = max(0.0, stock)
            days_left = (shelf_stock / avg_sales) if avg_sales > 0 else None
            # Сорт без строки остатка, у которого расхода давно не было, из ротации вышел:
            # показываем в свёрнутом блоке, но не заказываем сами.
            last_out = st.get('last_out')
            stale = bool(data.get('no_stock_row')) and (
                last_out is None or (today - last_out).days > NO_STOCK_RECENT_DAYS)
            # Полка плюс то, что в пути: именно из этого считается дефицит.
            effective_stock = shelf_stock + on_order
            price_info = prices.get(product_id) or {}
            row = {
                'product_id': product_id, 'data': data, 'st': st, 'supplier': supplier,
                'params': params, 'stock': stock, 'on_order': on_order,
                'effective_stock': effective_stock, 'avg_sales': avg_sales,
                'velocity': velocity, 'days_left': days_left, 'pack_size': pack_size,
                'shelf_stock': shelf_stock, 'keg_liters': keg_liters, 'keg_source': keg_source,
                'no_stock_row': bool(data.get('no_stock_row')), 'last_out': last_out,
                'blocked': stale,
                'horizon_days': horizon_days, 'days_to_delivery': days_to_delivery,
                'first_delivery': first_delivery, 'next_delivery': next_delivery,
                'days_to_expiry': days_to_expiry, 'nearest_expiry': nearest_expiry,
                'is_negative': is_negative,
                'price': price_info.get('price'),
                'price_source': price_info.get('source'),
                'price_date': price_info.get('date'),
            }
            row['recommended_base'] = _recommend_at(row, 0)
            row['urgency'] = 'critical' if is_negative else _urgency_level(
                effective_stock, avg_sales, days_to_delivery, velocity)
            rows.append(row)

        # Минимальный заказ поставщика: группа считается на один увеличенный горизонт,
        # пока сумма рекомендаций не дотянет до минимума (docs/suppliers.md).
        by_supplier = {}
        for row in rows:
            by_supplier.setdefault(row['supplier'], []).append(row)
        supplier_states = {}
        for supplier, group_rows in by_supplier.items():
            params = params_by_supplier[supplier]
            other_sum = _draft_sum(draft_items_map.get(supplier), exclude_bar=bar)
            state = _min_order_state(group_rows, params, other_bars_sum=other_sum,
                                     apply_fill=bool(target_store_id))
            state['supplier'] = supplier
            state['draft_bar_sum'] = _draft_sum(draft_items_map.get(supplier), only_bar=bar)
            state['draft_total_sum'] = _draft_sum(draft_items_map.get(supplier))
            supplier_states[supplier] = state

        items = []
        for row in rows:
            data, st = row['data'], row['st']
            extra_days = supplier_states[row['supplier']]['extra_days']
            recommended = _recommend_at(row, extra_days)
            cover_days = row['horizon_days'] + extra_days
            target_stock = row['avg_sales'] * (cover_days + SAFETY_DAYS)
            last_in = st.get('last_in')

            items.append({
                'product_id': row['product_id'],
                'type': data['kind'],
                'name': data['name'],
                'supplier': row['supplier'],
                'supplier_raw': data['category'],
                'supplier_is_default': row['params']['is_default'],
                'self_pickup': row['params']['self_pickup'],
                'unit': data['unit'],
                'stock': round(row['stock'], 2),
                'shelf_stock': round(row['shelf_stock'], 2),
                'on_order': round(row['on_order'], 2),
                'effective_stock': round(row['effective_stock'], 2),
                'no_stock_row': row['no_stock_row'],
                'out_of_rotation': row['blocked'],
                'last_outgoing': row['last_out'].isoformat() if row['last_out'] else None,
                'keg_liters': row['keg_liters'],
                'keg_source': row['keg_source'],
                'kegs': (int(round(recommended / row['keg_liters']))
                         if row['keg_liters'] and recommended else None),
                'open_orders': open_orders_map.get(row['product_id'], []),
                'draft_qty': draft_map.get(row['product_id'], 0.0),
                'avg_sales': round(row['avg_sales'], 2),
                'weekly_sales': round(row['avg_sales'] * DAYS_PER_WEEK, 2),
                'days_in_period': st['days_in_period'],
                'is_new': st['is_new'],
                'consumption_by_type': {k: round(v, 2) for k, v in st['by_document_type'].items()},
                'velocity': row['velocity'],
                'days_left': round(row['days_left'], 1) if row['days_left'] is not None else None,
                'lead_time_days': row['params']['lead_time_days'],
                'days_to_delivery': row['days_to_delivery'],
                'horizon_days': row['horizon_days'],
                'expected_delivery': row['first_delivery'].isoformat(),
                'next_delivery': row['next_delivery'].isoformat(),
                'target_stock': round(target_stock, 2),
                'pack_size': row['pack_size'],
                'recommended': recommended,
                'recommended_base': row['recommended_base'],
                'min_order_extra_days': extra_days if recommended > row['recommended_base'] else 0,
                'price': row['price'],
                'price_source': row['price_source'],
                'price_date': row['price_date'],
                'line_sum': line_sum(row['price'], recommended),
                'urgency': row['urgency'],
                'nearest_expiry': row['nearest_expiry'],
                'days_to_expiry': row['days_to_expiry'],
                'last_incoming': ({'date': last_in.isoformat(), 'amount': round(st.get('last_in_amount') or 0.0, 2)}
                                  if last_in else None),
            })
            it = items[-1]
            it['reason_code'], it['reason'] = _reason({
                'unit': data['unit'], 'stock': row['stock'], 'shelf': row['shelf_stock'],
                'on_order': row['on_order'], 'blocked': row['blocked'], 'last_out': row['last_out'],
                'keg_liters': row['keg_liters'],
                'avg': row['avg_sales'], 'target': target_stock, 'recommended': recommended,
                'horizon_days': row['horizon_days'], 'first_delivery': row['first_delivery'],
                'next_delivery': row['next_delivery'], 'pack_size': row['pack_size'],
                'velocity': row['velocity'], 'days_left': row['days_left'],
                'days_to_expiry': row['days_to_expiry'], 'nearest_expiry': row['nearest_expiry'],
                'is_new': st['is_new'], 'days_in_period': st['days_in_period'],
                'is_negative': row['is_negative'],
                'min_order_extra_days': it['min_order_extra_days'],
                'min_order_sum': supplier_states[row['supplier']]['min_order_sum'],
            }, snapshot['window_days'])
            # Секция экрана «К заказу»: decide — требует решения (есть что заказать,
            # учётная ошибка или полка опустеет раньше поставки, даже если заказ
            # заблокирован сроком годности); idle — без движения / редко; ok — хватает.
            # Черновик показывается всегда (решает фронт).
            if row['blocked']:
                it['section'] = 'idle'      # нет в остатках и расхода давно не было
            elif recommended > 0 or row['is_negative'] or row['urgency'] in ('critical', 'high'):
                it['section'] = 'decide'
            elif row['velocity'] in ('dead', 'slow'):
                it['section'] = 'idle'
            else:
                it['section'] = 'ok'

        # Сортировка: сначала срочность, внутри — по days_left возрастающе
        urgency_rank = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

        def sort_key(it):
            u = urgency_rank.get(it['urgency'], 99)
            d = it['days_left'] if it['days_left'] is not None else 9999
            return (u, d)

        items.sort(key=sort_key)

        return jsonify({
            'bar': bar,
            'today': snapshot['today'],
            'updated_at': snapshot['fetched_at'],
            'chz_updated_at': chz_updated_at,
            'consumption_scope': 'store' if target_store_id else 'network',
            'window_days': snapshot['window_days'],
            'safety_days': SAFETY_DAYS,
            'min_order_max_extra_days': MIN_ORDER_MAX_EXTRA_DAYS,
            'near_expiry_block_days': NEAR_EXPIRY_BLOCK_DAYS,
            'slow_mover_weekly_sales': SLOW_MOVER_WEEKLY_SALES,
            'fast_mover_weekly_sales': FAST_MOVER_WEEKLY_SALES,
            'total_items': len(items),
            'critical_count': sum(1 for i in items if i['urgency'] == 'critical'),
            'high_count': sum(1 for i in items if i['urgency'] == 'high'),
            'medium_count': sum(1 for i in items if i['urgency'] == 'medium'),
            'active_count': sum(1 for i in items if i['velocity'] in ('regular', 'fast')),
            'slow_count': sum(1 for i in items if i['velocity'] == 'slow'),
            'dead_count': sum(1 for i in items if i['velocity'] == 'dead'),
            'recommended_total': sum(i['recommended'] for i in items),
            'on_order_count': sum(1 for i in items if i['on_order'] > 0),
            'draft_count': sum(1 for i in items if i['draft_qty'] > 0),
            'decide_count': sum(1 for i in items if i['section'] == 'decide'),
            'idle_count': sum(1 for i in items if i['section'] == 'idle'),
            'no_stock_count': sum(1 for i in items if i['no_stock_row']),
            'no_stock_recent_days': NO_STOCK_RECENT_DAYS,
            'default_keg_liters': DEFAULT_KEG_LITERS,
            'orders_available': orders_error is None,
            'orders_error': orders_error,
            'suppliers': supplier_states,
            'items': items,
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/order-board: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

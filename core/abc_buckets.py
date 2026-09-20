"""Решения по ассортименту: каждая позиция (фасовка или кег) ровно в одной группе.

Что это
-------
Шесть групп с действием для владельца. Группа определяется не парой букв ABC,
как до 2026-09-20 («Звёзды», «Рабочие лошадки», «Фон»...), а правилами с
защитой от малых выборок: буква A по Парето на плоском хвосте доставалась
позициям с тремя бутылками за месяц, и они получали «держать всегда»; позиции
с одной продажей получали «продвигать» или «удалить»; проданное по нулевой
цене — «удалить»; без себестоимости — ни в одну карточку.

Правила (первое совпадение побеждает, core/abc_buckets.py::decide_bucket):
  check       — себестоимости нет или наценка ниже половины порога B
                (продано в ноль, ниже себестоимости, битая карточка)
  new         — все продажи периода пришлись на его последнюю неделю
                (период от 2 полных недель): истории нет, решения нет
  few         — продаж меньше MIN_SALES_FOR_VERDICT: спрос не измерен
  weak        — выручка C (последние 5% накопленной выручки) при достаточных
                продажах; «вывести» — только на периоде от 28 дней, иначе
                группа показывается, но действие «смотреть за 4 недели»
  low_markup  — выручка A/B, наценка ниже минимума владельца (порог A: фасовка
                120%, кеги 250%; «120 и 250 это минималка», 2026-09-20)
  core        — выручка A/B, наценка не ниже минимума: основа выручки

Буквы ABC остаются как есть (Парето 80/95 и пороги наценки из
core/abc_thresholds.py); XYZ и складские поля в решениях не участвуют.
Константы и их обоснование — core/abc_thresholds.py.

Файлы
-----
- core/packaging_analysis.py — фасовка: продажи в штуках (TotalQty)
- core/draft_kegs.py — кеги: продажи в порциях (TotalPortions)
- docs/abc-xyz-analysis.md, docs/draft.md — формулы и тексты на экране
"""

from core.abc_thresholds import (
    MARKUP_A_MIN,
    MARKUP_AUDIT_FLOOR_FACTOR,
    MARKUP_B_MIN,
    MIN_DAYS_FOR_NEGATIVE_VERDICT,
    MIN_SALES_FOR_VERDICT,
)

# Порядок — порядок карточек на странице: сначала то, что приносит деньги,
# потом что требует действия, потом что ждёт данных, последним — учёт.
BUCKETS = {
    'core':       {'name': 'Основа выручки',  'action': 'Держать в наличии',
                   'tone': 'ok',     'order': 1,
                   'hint': 'Эти позиции делают выручку при нормальной наценке. '
                           'Из наличия выпадать не должны: каждый день без них — '
                           'прямая потеря.'},
    'low_markup': {'name': 'Низкая наценка',  'action': 'Поднять цену',
                   'tone': 'warn',   'order': 2,
                   'hint': 'Спрос доказан продажами, а наценка ниже минимума сети: '
                           'позиция приносит меньше, чем должна. Пересмотреть цену '
                           'или закупочные условия.'},
    'weak':       {'name': 'Слабые продажи',  'action': 'Вывести из ассортимента',
                   'tone': 'bad',    'order': 3,
                   # На коротком периоде отрицательное решение не выносится.
                   'action_short': 'Смотреть за 4 недели', 'tone_short': 'calm',
                   'hint': 'Продаж достаточно, чтобы судить, и всё равно последние 5% '
                           'выручки. Допродать остаток и не закупать повторно; список '
                           'надёжен только по периоду от четырёх недель.'},
    'few':        {'name': 'Мало продаж',     'action': 'Заказывать по факту',
                   'tone': 'calm',   'order': 4,
                   'hint': 'По одной-двум покупкам спрос не измерить, наценка по ним '
                           'может быть искажена одной скидкой. Не держать запас, '
                           'дозаказывать по продаже.'},
    'new':        {'name': 'Новинки периода', 'action': 'Оценить через 4 недели',
                   'tone': 'accent', 'order': 5,
                   'hint': 'Позиция появилась в продаже на последней неделе периода: '
                           'любое решение описывало бы неделю, а не позицию.'},
    'check':      {'name': 'Сверить учёт',    'action': 'Проверить себестоимость и цену',
                   'tone': 'warn',   'order': 6,
                   'hint': 'Без себестоимости в iiko наценку не посчитать; продажа в '
                           'ноль или ниже себестоимости — скидка, выдача или битая '
                           'карточка. Сначала починить учёт, потом решать по ассортименту.'},
}

# Единицы продаж для подписей: фасовка считает штуки, кеги — порции.
UNIT_WORDS = {
    'pieces': ('продаж', 'штук'),
    'portions': ('порций', 'порций'),
}


def _is_newcomer(weeks_in_period, weekly, outside_weeks):
    """Все продажи периода — в его последней 7-дневной корзине.

    Окно недель прижато к концу периода (core/abc_thresholds.py, WEEK_DAYS),
    поэтому «раньше последней недели продаж не было» и есть признак новинки —
    даты создания карточки iiko не отдаёт. Нужно хотя бы две полные недели:
    на одной неделе последняя корзина — весь период.
    """
    if weeks_in_period < 2 or not weekly:
        return False
    if outside_weeks and outside_weeks > 0:
        return False
    if sum(weekly) == 0:
        # Продажи есть (иначе сюда не попасть), а движений по неделям нет вовсе:
        # у кега списание со склада легло за границу периода (кран открыт в
        # последний день). Истории нет — это новинка, а не «слабые продажи».
        return True
    return sum(weekly[:-1]) == 0 and weekly[-1] > 0


def decide_bucket(abc_revenue, markup_share, sales, weeks_in_period, weekly,
                  outside_weeks=0.0, a_min=MARKUP_A_MIN, b_min=MARKUP_B_MIN):
    """Ключ группы по правилам из докстроки модуля.

    abc_revenue   — 'A' | 'B' | 'C' (Парето по выручке)
    markup_share  — наценка долей (1.2 = 120%) или None
    sales         — число продаж: штук у фасовки, порций у кегов
    weeks_in_period, weekly, outside_weeks — полных недель, продажи по
                    недельным корзинам (список), продажи вне окна недель
    a_min         — минимальная наценка владельца долей (фасовка 1.2, кеги 2.5):
                    ниже неё — «Низкая наценка»
    b_min         — порог B долей (фасовка 1.0, кеги 2.0): от него считается пол
                    правдоподобия для «Сверить учёт»
    """
    if markup_share is None or markup_share < b_min * MARKUP_AUDIT_FLOOR_FACTOR:
        return 'check'
    if sales > 0 and _is_newcomer(weeks_in_period, weekly, outside_weeks):
        return 'new'
    if sales < MIN_SALES_FOR_VERDICT:
        return 'few'
    if abc_revenue == 'C':
        return 'weak'
    if markup_share < a_min:
        return 'low_markup'
    return 'core'


def negative_verdict_ready(period_days):
    """Можно ли выносить «вывести из ассортимента» по этому периоду."""
    return period_days >= MIN_DAYS_FOR_NEGATIVE_VERDICT


def bucket_rule_text(key, a_min, b_min, unit, period_days):
    """Правило группы словами и числами — печатается на экране (CLAUDE.md п. 1)."""
    sales_word, _ = UNIT_WORDS[unit]
    a_pct = f'{a_min * 100:.0f}%'
    floor_pct = f'{b_min * MARKUP_AUDIT_FLOOR_FACTOR * 100:.0f}%'
    n = MIN_SALES_FOR_VERDICT
    days = MIN_DAYS_FOR_NEGATIVE_VERDICT
    if key == 'core':
        return (f'выручка A или B (первые 95% накопленной выручки), наценка от {a_pct} '
                f'(минимум сети), {sales_word} не меньше {n}')
    if key == 'low_markup':
        return (f'выручка A или B, наценка от {floor_pct} до {a_pct} (ниже минимума сети), '
                f'{sales_word} не меньше {n}: спрос есть, цена ниже нормы')
    if key == 'weak':
        base = (f'выручка C (последние 5% накопленной выручки) при {sales_word} '
                f'не меньше {n}')
        if negative_verdict_ready(period_days):
            return base + f' за период от {days} дней'
        return (base + f'; период короче {days} дней — решение о выводе не выносится, '
                'посмотрите этот же список за 4 недели')
    if key == 'few':
        return (f'{sales_word} меньше {n} за период: спрос не измерен, '
                'ни хвалить, ни выводить нельзя')
    if key == 'new':
        return ('все продажи периода — в его последней неделе (период от 2 полных '
                'недель): истории ещё нет')
    if key == 'check':
        return (f'себестоимость не задана в iiko или наценка ниже {floor_pct}: '
                'продано в ноль, ниже себестоимости или битая карточка')
    return ''


def bucket_cards(rows, period_days, unit='pieces', a_min=MARKUP_A_MIN, b_min=MARKUP_B_MIN,
                 revenue_key='TotalRevenue', bucket_key='ABC_Bucket'):
    """Карточки групп для ответа: счётчики, выручка, доля, действие, правило.

    Считается на сервере целиком — страница только печатает. Действие и тон
    группы «weak» зависят от длины периода.
    """
    # База долей — та же выручка, что в сводке страницы (со знаком: возвраты
    # её уменьшают), иначе доли карточек не сходились бы с плиткой «Выручка».
    total_revenue = sum(float(r.get(revenue_key) or 0.0) for r in rows)
    ready = negative_verdict_ready(period_days)
    cards = []
    for key, info in sorted(BUCKETS.items(), key=lambda kv: kv[1]['order']):
        members = [r for r in rows if r.get(bucket_key) == key]
        revenue = sum(float(r.get(revenue_key) or 0.0) for r in members)
        action = info['action']
        tone = info['tone']
        if key == 'weak' and not ready:
            action = info['action_short']
            tone = info['tone_short']
        cards.append({
            'key': key,
            'name': info['name'],
            'action': action,
            'tone': tone,
            'order': info['order'],
            'count': len(members),
            'revenue': revenue,
            'revenue_share_percent': (revenue / total_revenue * 100) if total_revenue > 0 else 0.0,
            'rule': bucket_rule_text(key, a_min, b_min, unit, period_days),
            'hint': info['hint'],
            'verdict_ready': ready if key == 'weak' else True,
        })
    return cards

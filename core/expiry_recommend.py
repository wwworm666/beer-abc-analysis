"""Логика рекомендаций по управлению сроками годности.

Формирует tier-классификацию SKU и предлагает действия (уценка / перевод в другой бар).
Все константы объяснены, формулы — в коде. См. docs/expiration.md.
"""

from typing import Optional


# Tier-пороги в днях (адаптация ShelfLifePro под пиво).
# Меньше дней = выше срочность = больше скидка.
TIER_EXPIRED_MAX = 0          # days < 0 → expired
TIER_CRITICAL_MAX = 7         # 0..7 дней включительно → critical
TIER_URGENT_MAX = 14          # 8..14 → urgent
TIER_WATCH_MAX = 30           # 15..30 → watch
# > 30 → fresh

# Базовая скидка по tier-у (целые проценты).
# Идея: чем ближе срок, тем глубже уценка, чтобы успеть продать.
DISCOUNT_CRITICAL = 35        # для 0..7 дней
DISCOUNT_URGENT = 20          # для 8..14
DISCOUNT_WATCH = 10           # для 15..30
DISCOUNT_FRESH = 0            # для 30+ — продаём по обычной цене

# Эластичность спроса по цене для пива (эмпирическая константа).
# Прирост спроса от скидки = PRICE_ELASTICITY × (discount_pct/100).
# 1.5 означает: −20% цены → +30% спроса. Для крафта реальное значение ниже,
# для масс-маркета — выше; настраиваемая константа.
PRICE_ELASTICITY = 1.5

# Кандидат на перевод подходит, если на нём остаток <7 дней хватания
# (stock_level in {'low', 'medium'}). См. routes/stocks.py:_velocity.
TRANSFER_TARGET_LEVELS = ('low', 'medium')


def classify_tier(days_to_expiry: Optional[int]) -> str:
    """Классификация по сроку до истечения.

    None → 'unknown' (нет данных ЧЗ для позиции).
    """
    if days_to_expiry is None:
        return 'unknown'
    if days_to_expiry < TIER_EXPIRED_MAX:
        return 'expired'
    if days_to_expiry <= TIER_CRITICAL_MAX:
        return 'critical'
    if days_to_expiry <= TIER_URGENT_MAX:
        return 'urgent'
    if days_to_expiry <= TIER_WATCH_MAX:
        return 'watch'
    return 'fresh'


def base_discount(tier: str) -> int:
    """Базовая скидка по tier-у."""
    return {
        'expired': 0,         # просрочка — списание, скидка не помогает
        'critical': DISCOUNT_CRITICAL,
        'urgent': DISCOUNT_URGENT,
        'watch': DISCOUNT_WATCH,
        'fresh': DISCOUNT_FRESH,
        'unknown': 0,
    }.get(tier, 0)


def expected_sales(velocity: float, days: int) -> float:
    """Прогноз продаж без вмешательства.

    velocity (шт/день) × days = ожидаемые продажи за период.
    """
    return max(0.0, velocity) * max(0, days)


def boosted_sales(velocity: float, days: int, discount_pct: int) -> float:
    """Прогноз продаж после уценки.

    boosted_velocity = velocity × (1 + PRICE_ELASTICITY × discount/100)
    """
    if discount_pct <= 0:
        return expected_sales(velocity, days)
    multiplier = 1 + PRICE_ELASTICITY * discount_pct / 100
    return expected_sales(velocity * multiplier, days)


def recommend(item: dict, transfer_candidates: list[dict] | None = None) -> dict:
    """Сформировать рекомендацию для позиции.

    Аргументы:
        item — словарь с полями stock, avg_sales, days_to_expiry, has_chz_data
        transfer_candidates — список других баров с тем же GTIN:
            [{bar, velocity, stock_level}, ...]

    Возвращает:
        {
            tier: 'expired'|'critical'|'urgent'|'watch'|'fresh'|'unknown',
            surplus: float — сколько шт. не успеем продать без действий,
            options: [
                {kind: 'none'|'writeoff'|'markdown'|'transfer', ...}, ...
            ],
        }
    """
    days = item.get('days_to_expiry')
    stock = float(item.get('stock', 0) or 0)
    velocity = float(item.get('avg_sales', 0) or 0)
    has_chz = bool(item.get('has_chz_data'))

    tier = classify_tier(days)

    if not has_chz or days is None:
        return {
            'tier': 'unknown',
            'surplus': 0.0,
            'options': [{'kind': 'none', 'reason': 'нет данных ЧЗ для позиции'}],
        }

    if tier == 'expired':
        return {
            'tier': 'expired',
            'surplus': stock,
            'options': [{
                'kind': 'writeoff',
                'amount': round(stock, 1),
                'reason': 'срок истёк — к списанию',
            }],
        }

    forecast = expected_sales(velocity, days)
    surplus = max(0.0, stock - forecast)

    if surplus <= 0 or tier == 'fresh':
        return {
            'tier': tier,
            'surplus': 0.0,
            'options': [{
                'kind': 'none',
                'reason': 'успеем продать без скидки',
                'expected_sold': round(min(stock, forecast), 1),
            }],
        }

    options: list[dict] = []

    # Вариант 1: уценка по базовой ставке tier-а.
    discount_pct = base_discount(tier)
    if discount_pct > 0:
        sold = min(stock, boosted_sales(velocity, days, discount_pct))
        writeoff = max(0.0, stock - sold)
        options.append({
            'kind': 'markdown',
            'discount_pct': discount_pct,
            'expected_sold': round(sold, 1),
            'expected_writeoff': round(writeoff, 1),
        })

    # Вариант 2: перевод в бар где velocity выше и сток низкий.
    if transfer_candidates:
        for c in transfer_candidates:
            c_velocity = float(c.get('velocity', 0) or 0)
            c_level = c.get('stock_level', 'high')
            c_capacity = c_velocity * days
            if c_capacity >= surplus and c_level in TRANSFER_TARGET_LEVELS:
                options.append({
                    'kind': 'transfer',
                    'to_bar': c.get('bar', ''),
                    'amount': round(min(surplus, c_capacity), 1),
                    'target_velocity': round(c_velocity, 2),
                    'target_level': c_level,
                })
                break

    if not options:
        options.append({
            'kind': 'none',
            'reason': 'нет подходящих действий',
        })

    return {
        'tier': tier,
        'surplus': round(surplus, 1),
        'options': options,
    }

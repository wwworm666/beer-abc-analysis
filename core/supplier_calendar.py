"""Календарь поставок: ожидаемая дата доставки и горизонт до следующей.

Решения владельца (2026-09-10): большинство поставщиков не доставляют в
субботу и воскресенье, но принимают заказ в воскресенье на понедельник;
поставка может задержаться на один-два дня, поэтому дата ожидаемая, а не
обязательство (тревога в UI мягкая, см. ORDER_OVERDUE_GRACE_DAYS).

Срок поставки (lead_time_days) считается в днях доставки: каждый следующий
календарный день, попадающий в дни доставки поставщика, уменьшает счётчик.
Заказ в пятницу с lead_time 1 → понедельник; в воскресенье с lead_time 1 →
понедельник; в среду с lead_time 3 → понедельник.
"""
from datetime import date, timedelta
from typing import Iterable

DEFAULT_DELIVERY_WEEKDAYS = (0, 1, 2, 3, 4)   # пн–пт (date.weekday(): пн = 0)
ORDER_OVERDUE_GRACE_DAYS = 2                  # столько дней после ожидаемой даты задержка не считается проблемой
_MAX_SCAN_DAYS = 60                           # защита от пустого набора дней доставки


def _weekdays(delivery_weekdays: Iterable[int] | None) -> set:
    days = set(delivery_weekdays) if delivery_weekdays is not None else set(DEFAULT_DELIVERY_WEEKDAYS)
    return days or set(DEFAULT_DELIVERY_WEEKDAYS)


def next_delivery_date(sent_on: date, lead_time_days: int,
                       delivery_weekdays: Iterable[int] | None = None) -> date:
    """Ожидаемая дата поставки для заказа, отправленного sent_on.

    lead_time_days < 1 считается как 1: поставка не раньше следующего дня доставки.
    """
    days = _weekdays(delivery_weekdays)
    remaining = max(1, int(lead_time_days or 1))
    current = sent_on
    for _ in range(_MAX_SCAN_DAYS):
        current += timedelta(days=1)
        if current.weekday() in days:
            remaining -= 1
            if remaining == 0:
                return current
    return current


def delivery_after(day: date, delivery_weekdays: Iterable[int] | None = None) -> date:
    """Ближайший день доставки строго после day."""
    return next_delivery_date(day, 1, delivery_weekdays)


def horizon_days(sent_on: date, lead_time_days: int,
                 delivery_weekdays: Iterable[int] | None = None) -> int:
    """Сколько дней должен покрыть заказ: до поставки, следующей за ближайшей.

    Заказ в четверг с lead_time 1: ближайшая поставка пт, следующая пн →
    горизонт 4 дня (пт, сб, вс, пн). Используется концепцией этапа 2 как
    замена константного lead_time в формуле рекомендации.
    """
    first = next_delivery_date(sent_on, lead_time_days, delivery_weekdays)
    second = delivery_after(first, delivery_weekdays)
    return (second - sent_on).days


def is_overdue(expected_at: date, today: date, grace_days: int = ORDER_OVERDUE_GRACE_DAYS) -> bool:
    """Поставка считается задержанной только спустя grace_days после ожидаемой даты."""
    return (today - expected_at).days > grace_days

"""
Генератор iCalendar (.ics) для личного графика сотрудника.

## Что это
Бармен скачивает СВОЙ график одним файлом и импортирует в календарь телефона:
iOS (Apple Calendar) и Android (Google Calendar) оба понимают .ics нативно.
Разовая выгрузка — статичный снимок (не подписка): поменялся график -> скачать заново.

## Как работает (правила RFC 5545)
- Одно событие (VEVENT) на смену. `UID` стабилен (`shift-<id>@...`), поэтому
  повторный импорт ОБНОВЛЯЕТ событие, а не плодит дубли.
- Время «плавающее локальное» (без TZID/Z): событие в HH:MM по месту, вся сеть
  в одном поясе (Москва) — так событие не «уезжает» при смене настроек телефона.
- Начало смены: `start_time` ('HH:MM'), если задано (вечер — 18:00); иначе
  `DAY_START_DEFAULT` = 14:00 (смена «день», в таблице start_time = NULL).
- Длительность: факт часов (`fact_minutes`), если бармен его ввёл; иначе план-дефолт
  по роли (`PLAN_MINUTES`) — для ещё не отработанных (плановых) смен.
- Цвет события по точке (`COLOR`, RFC 7986) — совпадает по смыслу с цветами точек в
  сетке (`VENUE_COLOR` по `venue_key`). RFC разрешает только имена CSS3, поэтому берём
  ближайшее именованное. Применяет Apple Calendar; Google per-event цвета из .ics
  игнорирует (ограничение формата).
- Спецсимволы значения экранируются (`\\ ; ,` и перевод строки) по 3.3.11.
- Строки разделяются CRLF (3.1). Складывание длинных строк НЕ делаем намеренно:
  свёртка по октетам ломала бы UTF-8 кириллицу посреди символа, а Apple/Google
  длинные строки принимают; содержимое держим коротким.

Детерминированно: один и тот же набор смен -> один и тот же файл (кроме `DTSTAMP` —
времени генерации, которое передаётся аргументом).

## Файлы
- `core/calendar_ics.py` — этот генератор (чистая функция).
- `routes/schedule.py` — маршрут `/schedule/cal.ics` (за логином, смены current_user).
- `templates/schedule.html` — кнопка «В календарь».
Док: `docs/schedule.md`, раздел «Экспорт в календарь».
"""

import re
from datetime import datetime, timedelta, timezone

PRODID = "-//Пивная культура//График смен//RU"

# Смена «день» без явного времени начинается в 14:00 (пресет «день», см. docs/schedule.md).
DAY_START_DEFAULT = "14:00"

# Валидное плановое время начала 'HH:MM' (24ч).
START_TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')

# План-дефолт длительности (минуты) по role_id, когда факт часов ещё не введён:
# день (бармен) ~9ч (14:00-23:00), вечер (второй бармен) ~5ч (18:00-23:00).
PLAN_MINUTES = {1: 540, 2: 300}
DEFAULT_PLAN_MINUTES = 540

# Цвет события по точке — тот же смысл, что цвета точек в сетке графика
# (static/js/schedule/screens.js: BAR_COLORS). RFC 7986 (свойство COLOR) требует имя
# из набора CSS3, поэтому берём ближайшее ИМЕНОВАННОЕ (hex стандарт не разрешает).
# Apple Calendar (iPhone) применяет per-event COLOR; Google Calendar импортированные
# per-event цвета игнорирует — известное ограничение формата, тут ничего не поделать.
VENUE_COLOR = {
    'varshavskaya': 'cadetblue',      # ~#6f93a6 сине-серый
    'bolshoy': 'rosybrown',           # ~#c08f9b пыльно-розовый (ВО)
    'kremenchugskaya': 'darkkhaki',   # ~#c3a55f приглушённое золото
    'ligovskiy': 'darkseagreen',      # ~#7d9b6b шалфейно-зелёный
}


def _escape(text) -> str:
    """Экранировать текст для значения свойства iCalendar (RFC 5545 3.3.11)."""
    if text is None:
        return ""
    return (str(text).replace("\\", "\\\\")
                     .replace(";", "\\;")
                     .replace(",", "\\,")
                     .replace("\n", "\\n"))


def _parse_hhmm(value, default=DAY_START_DEFAULT):
    """'HH:MM' -> (часы, минуты). Пусто/мусор -> default (а не жёсткие 14:00)."""
    s = (value or "").strip() or default
    try:
        hh, mm = s.split(":")[:2]
        return int(hh), int(mm)
    except (ValueError, AttributeError):
        # мусорный value -> разобрать default детерминированно из единого источника
        try:
            dh, dm = default.split(":")[:2]
            return int(dh), int(dm)
        except (ValueError, AttributeError):
            return 14, 0


def build_calendar(calendar_name: str, shifts, dtstamp: datetime = None) -> str:
    """Собрать .ics-текст для списка смен одного сотрудника.

    shifts: список словарей (как из `ShiftsManager.get_shifts_for_employee`):
        обязательны `id`, `date` ('YYYY-MM-DD'); опц. `start_time`, `fact_minutes`,
        `location_name`, `role_id`, `role_name`, `venue_key` (для цвета события).
    dtstamp: момент генерации для DTSTAMP (None -> datetime.now()).
    Возвращает строку с CRLF-переводами, готовую к отдаче как text/calendar.
    """
    # DTSTAMP по RFC 5545 — момент в UTC (суффикс Z). Берём UTC явно, иначе серверное
    # МСК-время с суффиксом Z расходилось бы с истиной на 3 часа.
    stamp = (dtstamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape('График — ' + (calendar_name or 'сотрудник'))}",
        "X-WR-TIMEZONE:Europe/Moscow",
    ]
    for s in shifts:
        hh, mm = _parse_hhmm(s.get("start_time"))
        start_dt = datetime.strptime(s["date"][:10], "%Y-%m-%d").replace(hour=hh, minute=mm)
        fact = s.get("fact_minutes")
        # Факт 0 — валидный (бармен ввёл «0:00»), не путать с «факта нет» (None).
        has_fact = fact is not None
        dur = int(fact) if has_fact else PLAN_MINUTES.get(s.get("role_id"), DEFAULT_PLAN_MINUTES)
        end_dt = start_dt + timedelta(minutes=dur)

        loc = s.get("location_name") or ""
        role = s.get("role_name") or ""
        # «явное время» — только если start_time реально валидный HH:MM, а не любой непустой мусор.
        has_time = bool(START_TIME_RE.match((s.get("start_time") or "").strip()))
        when = f"с {hh:02d}:{mm:02d}" if has_time else "день (с 14:00)"
        hours = f"{int(fact)//60}:{int(fact)%60:02d} (факт)" if has_fact else "по плану"
        desc = f"{role}. {when}. Часы: {hours}."

        ev = [
            "BEGIN:VEVENT",
            f"UID:shift-{s['id']}@kultura-schedule",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_escape(loc)}",
            f"LOCATION:{_escape(loc)}",
            f"DESCRIPTION:{_escape(desc)}",
        ]
        # Цвет по точке (совпадает по смыслу с сеткой). Только если знаем venue_key.
        color = VENUE_COLOR.get(s.get("venue_key"))
        if color:
            ev.append(f"COLOR:{color}")
        ev.append("END:VEVENT")
        lines += ev
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

"""Тревога по высокой температуре в баре.

Если температура воздуха в баре поднялась выше порога (TUYA_ALARM_TEMP_C, по
умолчанию 26 C) — шлём аларм в те же чаты, куда open-check бот шлёт тревоги о
закрытых барах (TELEGRAM_ALARM_CHAT_IDS + самоподписавшиеся в боте).

Антиспам (главное): опрос идёт каждые TUYA_POLL_MINUTES минут, но аларм НЕ шлётся
каждый раз. Состояние тревоги по бару хранится в temperature_store (таблица
alarm_state):
- аларм отправляется ОДИН раз при пересечении порога снизу вверх;
- пока бар «горит» — тишина;
- когда температура опускается ниже TUYA_ALARM_CLEAR_C (по умолчанию порог - 1 C,
  т.е. 25 C; гистерезис против дребезга у 26.0) — тревога снимается МОЛЧА (без
  сообщения), чтобы следующее превышение снова сработало.

Тихие часы: в окне [TUYA_ALARM_QUIET_START, TUYA_ALARM_QUIET_END) по МСК (по умолчанию
01:00–15:00 — бары закрыты/пусты) оценка вообще пропускается: ни тревог, ни снятия. Если
к началу активных часов всё ещё жарко — тревога уйдёт тогда.

Дедуп под gunicorn --workers 2: переход состояния — атомарный compare-and-set в
SQLite (store.set_alarm_state вернёт True ровно одному воркеру), поэтому аларм не
двоится. Если отправка не удалась — состояние откатывается, чтобы следующий опрос
повторил попытку (а не «проглотил» тревогу навсегда).

Оценка вызывается ТОЛЬКО из фонового опроса (core/temperature_scheduler.py), не из
живого опроса страницы — чтобы тревоги шли по предсказуемому расписанию, а не на
каждое открытие /temperature.

Документация: docs/temperature.md
"""
import os

from core.temperature_store import get_store


def _alarm_temp() -> float:
    """Порог тревоги (C). Выше него — «жарко»."""
    try:
        return float(os.getenv("TUYA_ALARM_TEMP_C", "26"))
    except (ValueError, TypeError):
        return 26.0


def _clear_temp(alarm_temp: float) -> float:
    """Порог возврата в норму (гистерезис). По умолчанию порог - 1 C; не выше порога."""
    raw = os.getenv("TUYA_ALARM_CLEAR_C")
    if raw:
        try:
            return min(float(raw), alarm_temp)
        except (ValueError, TypeError):
            pass
    return alarm_temp - 1.0


def _in_quiet_hours() -> bool:
    """True, если сейчас тихие часы по МСК — тревоги не оцениваются и не шлются.

    Окно [start, end): по умолчанию 01:00–15:00 (бары закрыты/пусты). Поддерживает
    окно через полночь (например, start=23, end=5).
    """
    try:
        start = int(os.getenv("TUYA_ALARM_QUIET_START", "1"))
    except (ValueError, TypeError):
        start = 1
    try:
        end = int(os.getenv("TUYA_ALARM_QUIET_END", "15"))
    except (ValueError, TypeError):
        end = 15
    if start == end:
        return False
    from core.open_check_bot import now_msk
    h = now_msk().hour
    if start < end:
        return start <= h < end
    return h >= start or h < end   # окно через полночь


def _short(bar_key: str) -> str:
    from core.open_check_bot import BAR_SHORT_NAMES
    return BAR_SHORT_NAMES.get(bar_key, bar_key)


def _now_hhmm() -> str:
    from core.open_check_bot import now_msk
    return now_msk().strftime("%H:%M")


def _send(text: str) -> bool:
    """Отправить в чаты тревог (как open-check). True, если ушло хотя бы одному."""
    from core.open_check_bot import _alarm_recipients, _is_dry_run
    from core.open_check_telegram import send_message

    recipients = _alarm_recipients()
    if not recipients:
        print("[TUYA-ALARM] нет получателей (TELEGRAM_ALARM_CHAT_IDS пуст и нет подписчиков)")
        return False
    if _is_dry_run():
        text = "[DRY-RUN] " + text
        recipients = recipients[:1]
    sent = 0
    for chat in recipients:
        if send_message(chat, text, html=True):
            sent += 1
    return sent > 0


def _alarm_text(bar_key: str, temp: float, alarm_temp: float) -> str:
    # Две первые строки жирным/капсом — видны в пуш-уведомлении и списке чатов
    # (тот же приём, что у open-check «!!! ALARM !!!»).
    return (
        "<b>!!! ЖАРКО В БАРЕ !!!</b>\n"
        f"<b>{_short(bar_key)} — {temp:.1f} C</b>\n"
        f"Порог {alarm_temp:.0f} C. Опрос {_now_hhmm()} МСК."
    )


def evaluate(readings) -> None:
    """Проверить показания на превышение порога и отправить тревоги.

    readings: {bar_key: {temperature, ...}} из tuya_temperature.read_all().
    Без токена бота или в тихие часы — тихо выходим и состояние НЕ трогаем (чтобы при
    появлении токена / начале активных часов ближайшее превышение сработало, а не
    «проспалось» в выставленном состоянии).
    """
    if not os.environ.get("TELEGRAM_OPEN_CHECK_BOT_TOKEN"):
        return
    if _in_quiet_hours():
        return

    alarm_temp = _alarm_temp()
    clear_temp = _clear_temp(alarm_temp)
    store = get_store()

    for bar_key, r in (readings or {}).items():
        t = r.get("temperature")
        if t is None:
            continue
        if t > alarm_temp:
            # Переход в тревогу. CAS вернёт True лишь одному воркеру — он и шлёт.
            if store.set_alarm_state(bar_key, True):
                print(f"[TUYA-ALARM] {bar_key} {t:.1f} C > {alarm_temp:.0f} — тревога")
                if not _send(_alarm_text(bar_key, t, alarm_temp)):
                    # Отправка не удалась — откатываем, чтобы следующий опрос повторил.
                    store.set_alarm_state(bar_key, False)
        elif t < clear_temp:
            # Возврат ниже порога — снимаем тревогу МОЛЧА (без оповещения), чтобы
            # следующее превышение снова сработало. Сообщение «в норму» убрано по просьбе.
            if store.set_alarm_state(bar_key, False):
                print(f"[TUYA-ALARM] {bar_key} {t:.1f} C < {clear_temp:.0f} — тревога снята (без оповещения)")
        # между clear_temp и alarm_temp — зона гистерезиса, состояние не меняем

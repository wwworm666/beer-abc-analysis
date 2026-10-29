"""Прогресс ответа в Telegram: что бот делает сейчас и сколько примерно осталось — только настоящее.

## Что это

Решение владельца 2026-10-29: вместо одного «печатает…» — видимый прогресс, «но только чтобы он
был настоящим, чтобы реально показывал, сколько примерно времени осталось». Пока бот работает
дольше settings.PROGRESS_AFTER_S, в чате висит одно сообщение; бот правит его раз в
settings.PROGRESS_EDIT_EVERY_S и удаляет, как только ушёл ответ (в чате остаётся один пузырь):

    Собираю отчёт · 1:40
    ▰▰▰▰▱▱▱▱▱▱ ≈ 3 мин осталось, не дольше 7 мин
    Сейчас: «Сравнение периодов» — 12 с, обычно до 40 с
    Сделано: 8 шагов, 4 запроса данных · $1.10 из $5.00

## Откуда числа

- «Сейчас» — что идёт в эту секунду: шаг модели («думаю»), вызов инструмента (его название из
  каталога сайта), работа агента, график, страница отчёта; секунды — сколько идёт это действие.
- «обычно до N с» — 3-я четверть длительности этого инструмента по прошлым вызовам (от
  MIN_TOOL_SAMPLES вызовов; store.tool_typical).
- «≈ осталось» — по прошлым удачным работам того же вида (вопрос или отчёт; store.recent_durations):
  медиана (длительность − прошло) среди тех, что шли дольше, чем уже идёт эта. Меньше MIN_HISTORY
  прошлых работ — типичные значения DEFAULT_SECONDS: первые дни оценка грубая, потом — ваша.
- «не дольше» — граница по пределу расхода на вопрос: остаток денег / темп трат этой работы + шаги
  на завершение (у отчёта — settings.REPORT_FINISH_ROUNDS). Дойдя до предела, бот обязан
  закончить, поэтому это граница, а не прогноз; оценка «осталось» её не превышает.
- Шкала — прошло / (прошло + осталось); назад не ходит, до ответа — не больше BAR_MAX.
- «Сделано» — запросы к модели и вызовы инструментов, бот и агенты вместе; расход — как в строке
  цены (пока settings.SHOW_COST).

## Точность

При первом показе запоминается, сколько бот обещал (shown_eta) и на какой секунде (shown_at);
после ответа — сколько осталось на деле. Сервер бота шлёт сайту, у скольких из последних отчётов
оценка ошиблась меньше чем на минуту (store.eta_accuracy) — это видно на странице «Доступ агентов».
"""
import html
import logging
import math
import statistics
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from kultura_bot import settings

log = logging.getLogger('kultura-bot')

# Типичные длительности (секунды), пока своей истории меньше MIN_HISTORY работ: вопрос — от
# короткого ответа до разбора с агентом; отчёт — 3–9 минут на обычной скорости (2026-10-28).
DEFAULT_SECONDS = {'answer': (20, 30, 45, 60, 90, 120), 'report': (150, 210, 270, 330, 420, 540)}
MIN_HISTORY = 5
MIN_TOOL_SAMPLES = 5
BAR_CELLS = 10
BAR_MAX = 0.95
TICK_S = 1.0                       # как часто поток проверяет, пора ли показать или поправить сообщение
TYPING_EVERY_S = 4                 # «печатает…» Telegram держит ~5 с
SPECIAL = {                        # действия, у которых своё человеческое название
    'common_chart_send': 'рисую график',
    'common_report_send': 'собираю страницу отчёта',
    'tool_search_tool_regex': 'ищу нужный инструмент',
    'ask_agent': 'передаю задачу агенту',
}


# ------------------------------------------------------------------ оценка (чистые функции)

def remaining_estimate(durations: List[float], elapsed: float, mode: str) -> Optional[float]:
    """Сколько примерно осталось: медиана (длительность − прошло) среди прошлых работ, которые шли
    дольше, чем уже идёт эта. None — эта работа уже дольше всех прошлых."""
    pool = [float(d) for d in durations if d and d > 0]
    if len(pool) < MIN_HISTORY:
        pool = [float(d) for d in DEFAULT_SECONDS.get(mode, DEFAULT_SECONDS['answer'])]
    longer = [d - elapsed for d in pool if d > elapsed]
    return statistics.median(longer) if longer else None


def upper_bound(*, elapsed: float, spent: float, limit: Optional[float], steps: int,
                finish_steps: int) -> Optional[float]:
    """Дольше этого работа не продлится: остаток предела расхода при нынешнем темпе трат плюс шаги
    на завершение. None — темп ещё не ясен (меньше двух шагов или 15 секунд)."""
    if not limit or spent <= 0 or elapsed < 15 or steps < 2:
        return None
    rate = spent / elapsed                       # $ в секунду
    step_seconds = elapsed / steps
    return max(limit - spent, 0.0) / rate + finish_steps * step_seconds


def clock_text(seconds: float) -> str:
    minutes, secs = divmod(max(int(seconds), 0), 60)
    return f'{minutes}:{secs:02d}'


def left_text(seconds: float) -> str:
    return 'меньше минуты' if seconds < 45 else f'≈ {max(1, round(seconds / 60))} мин'


def bar(fraction: float) -> str:
    filled = max(0, min(BAR_CELLS, round(fraction * BAR_CELLS)))
    return '▰' * filled + '▱' * (BAR_CELLS - filled)


def plural(n: int, forms: Tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 10 < n < 20:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    if 1 < n % 10 < 5:
        return forms[1]
    return forms[2]


def typical_seconds(samples: List[float]) -> Optional[float]:
    """3-я четверть длительностей (от MIN_TOOL_SAMPLES), иначе None."""
    if len(samples) < MIN_TOOL_SAMPLES:
        return None
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, math.ceil(0.75 * len(ordered)) - 1)]


# ------------------------------------------------------------------ что идёт сейчас

class Tracker:
    """Состояние одной работы: пишет поток ответа (шаги модели, инструменты, агенты), читает поток
    сообщения о прогрессе (render). spend — общий расход вопроса (agent.Spend), у бота и агентов."""

    def __init__(self, mode: str, spend: Any, *, limit: Optional[float], durations: List[float],
                 tool_typical: Dict[str, float], titles: Dict[str, str],
                 is_finishing: Callable[[], bool] = lambda: False, clock: Callable[[], float] = time.monotonic):
        self.mode = mode
        self.spend = spend
        self.limit = limit
        self.durations = list(durations)
        self.tool_typical = dict(tool_typical)
        self.titles = dict(titles)
        self.is_finishing = is_finishing
        self.clock = clock
        self.started = clock()
        self._lock = threading.Lock()
        self._activity = ('разбираю вопрос', self.started, '')     # (что, с какой секунды, инструмент)
        self._agent = ''
        self.tool_calls = 0
        self.tool_times: List[Tuple[str, float]] = []               # (инструмент, секунд) — в store
        self._fraction = 0.0
        self.shown_eta: Optional[float] = None                     # что обещали при первом показе
        self.shown_at: Optional[float] = None                      # на какой секунде показали

    def _set(self, label: str, tool: str = '') -> None:
        if self._agent:
            label = f'агент «{self._agent}»: {label}'
        self._activity = (label, self.clock(), tool)

    def model_start(self) -> None:
        with self._lock:
            self._set('думаю')

    def tool_start(self, name: str) -> None:
        with self._lock:
            label = SPECIAL.get(name) or f'«{self.titles.get(name) or name}»'
            self._set(label, tool=name)

    def tool_done(self, name: str) -> None:
        with self._lock:
            label, since, tool = self._activity
            if tool == name:
                self.tool_times.append((name, self.clock() - since))
            self.tool_calls += 1
            self._set('думаю')

    def agent_start(self, title: str) -> None:
        with self._lock:
            self._agent = ''
            self._set(f'передал задачу агенту «{title}»')
            self._agent = title

    def agent_done(self) -> None:
        with self._lock:
            self._agent = ''
            self._set('думаю')

    def elapsed(self) -> float:
        return self.clock() - self.started

    def estimate(self) -> Tuple[Optional[float], Optional[float]]:
        """(≈ осталось, не дольше) на эту секунду; любое может быть None."""
        elapsed = self.elapsed()
        finish = settings.REPORT_FINISH_ROUNDS if self.mode == 'report' else 1
        bound = upper_bound(elapsed=elapsed, spent=float(self.spend.usd), limit=self.limit,
                            steps=int(self.spend.steps), finish_steps=finish)
        est = remaining_estimate(self.durations, elapsed, self.mode)
        if est is not None and bound is not None:
            est = min(est, bound)
        return est, bound

    def render(self) -> str:
        """Текст сообщения о прогрессе (HTML Telegram)."""
        with self._lock:
            now = self.clock()
            elapsed = now - self.started
            title = 'Собираю отчёт' if self.mode == 'report' else 'Отвечаю'
            lines = [f'<b>{title} · {clock_text(elapsed)}</b>']
            est, bound = self.estimate()
            if self.is_finishing():
                lines.append(f'{bar(max(self._fraction, 0.9))} заканчиваю: собираю ответ из того, что уже есть')
                self._fraction = max(self._fraction, 0.9)
            elif est is None:
                tail = f', не дольше {math.ceil(bound / 60)} мин' if bound is not None else ''
                lines.append(f'{bar(self._fraction)} дольше обычного{tail}')
            else:
                self._fraction = min(max(self._fraction, elapsed / (elapsed + est)), BAR_MAX)
                tail = f', не дольше {math.ceil(bound / 60)} мин' if bound is not None and bound > est + 30 else ''
                lines.append(f'{bar(self._fraction)} {left_text(est)} осталось{tail}')
            label, since, tool = self._activity
            now_line = f'Сейчас: {html.escape(label, quote=False)} — {int(now - since)} с'
            typical = self.tool_typical.get(tool) if tool else None
            if typical:
                now_line += f', обычно до {int(round(typical))} с'
            lines.append(now_line)
            steps = int(self.spend.steps)
            done = (f'Сделано: {steps} {plural(steps, ("шаг", "шага", "шагов"))}, {self.tool_calls} '
                    f'{plural(self.tool_calls, ("запрос данных", "запроса данных", "запросов данных"))}')
            if settings.SHOW_COST and self.limit:
                done += f' · ${float(self.spend.usd):.2f} из ${self.limit:.2f}'
            lines.append(done)
            return '\n'.join(lines)

    def mark_shown(self) -> None:
        """Первый показ: запомнить обещание — по нему считается точность оценки."""
        est, _ = self.estimate()
        self.shown_eta, self.shown_at = est, self.elapsed()


# ------------------------------------------------------------------ сообщение в чате

class Reporter:
    """Поток прогресса: «печатает…» раз в TYPING_EVERY_S; после after_s — сообщение о прогрессе,
    правка раз в every_s (если текст изменился); stop() — убрать сообщение. Ошибки Telegram не
    мешают ответу: прогресс — подсказка, а не часть ответа."""

    def __init__(self, tg: Any, chat_id: str, tracker: Tracker, *, after_s: float, every_s: float,
                 reply_to: Optional[int] = None, enabled: bool = True):
        self.tg = tg
        self.chat_id = chat_id
        self.tracker = tracker
        self.after_s = after_s
        self.every_s = every_s
        self.reply_to = reply_to
        self.enabled = enabled
        self.message_id: Optional[int] = None
        self._last_text = ''
        self._last_edit = float('-inf')
        self._next_typing = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def tick(self) -> None:
        """Один шаг потока (тесты зовут его сами с подменённым временем)."""
        now = self.tracker.clock()
        if now >= self._next_typing:
            self._safe(self.tg.typing, self.chat_id)
            self._next_typing = now + TYPING_EVERY_S
        if not self.enabled:
            return
        if self.message_id is None:
            # Показать, когда пора; Telegram не принял — следующая попытка не раньше чем через every_s.
            if now - self.tracker.started >= self.after_s and now - self._last_edit >= self.every_s:
                text = self.tracker.render()
                self.message_id = self._safe(self.tg.send_status, self.chat_id, text, reply_to=self.reply_to)
                if self.message_id is not None:
                    self.tracker.mark_shown()          # точность считается только по показанному
                self._last_text, self._last_edit = text, now
        elif now - self._last_edit >= self.every_s:
            text = self.tracker.render()
            if text != self._last_text:
                self._safe(self.tg.edit_status, self.chat_id, self.message_id, text)
                self._last_text = text
            self._last_edit = now

    def _run(self) -> None:
        while not self._stop.wait(TICK_S):
            self.tick()

    def start(self) -> 'Reporter':
        self.tick()                                # «печатает…» сразу, дальше — поток
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Остановить поток и убрать сообщение о прогрессе (ответ уже в чате)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self.message_id is not None:
            self._safe(self.tg.delete_message, self.chat_id, self.message_id)
            self.message_id = None

    @staticmethod
    def _safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 — прогресс не роняет ответ
            log.warning('[BOT] прогресс: %s не прошёл', getattr(fn, '__name__', fn), exc_info=True)
            return None

"""
Калькулятор сравнения двух периодов дашборда (POST /api/comparison/periods).

Что сравнивается. Метрики «Аналитики» ровно как на экране: ключи и единицы ответа
/api/dashboard-analytics (camelCase, наценка в процентах, активность кранов по
журналу кранов). Набор и порядок метрик — как во вкладке «Сравнение» дашборда
(static/js/dashboard/modules/comparison.js, getMetricsConfig): 20 строк.

Соглашение о направлении — как на вкладке «Сравнение»:
    период 1 — сравниваемый («Период 1», по умолчанию текущая неделя),
    период 2 — база («было»).
    Δ   = период 1 − период 2
    Δ%  = Δ / период 2 × 100; у базы 0 — None (деление на ноль не определено;
          вкладка в этом случае рисует 0 %)
У метрик в процентах (доли, наценки, доля чеков с картой, активность кранов)
Δ — в процентных пунктах (п.п.), Δ% — относительное изменение, как на вкладке.

Округление: значения периодов — как пришли с сервера; Δ — 2 знака, Δ% — 1 знак
(вкладка печатает toFixed(1)).

«Лучше или хуже» (better): рост — хорошо, кроме бюджетных метрик
(core.plans_manager.BUDGET_METRICS — списания баллов: рост — минус); без
изменения — None. Та же логика, что цвет на вкладке «Сравнение».

Топ изменений — как блок «Топ-3 изменения» вкладки: метрики, у которых оба
значения не нули и |Δ%| не меньше 0,1, по убыванию |Δ%|; метрика с базой 0
в топ не попадает (её Δ% не определён).

До 2026-09-28 модуль сравнивал сырые ключи расчёта (наценка дробью) в обратном
направлении (Δ = период 2 − период 1) и писал выводы с эмодзи, а маршрут
/api/comparison/periods был заглушкой и модуль не вызывал.
"""
from typing import Dict, List

from core.plans_manager import BUDGET_METRICS

# (ключ экрана, подпись, единица). Порядок — getMetricsConfig вкладки «Сравнение».
COMPARISON_METRICS = (
    ('revenue', 'Выручка', '₽'),
    ('checks', 'Чеки', 'шт'),
    ('averageCheck', 'Средний чек', '₽'),
    ('draftShare', 'Доля розлива', '%'),
    ('packagedShare', 'Доля фасовки', '%'),
    ('kitchenShare', 'Доля кухни', '%'),
    ('revenueDraft', 'Выручка розлив', '₽'),
    ('revenuePackaged', 'Выручка фасовка', '₽'),
    ('revenueKitchen', 'Выручка кухня', '₽'),
    ('markupPercent', 'Наценка', '%'),
    ('profit', 'Прибыль', '₽'),
    ('markupDraft', 'Наценка розлив', '%'),
    ('markupPackaged', 'Наценка фасовка', '%'),
    ('markupKitchen', 'Наценка кухня', '%'),
    ('loyaltyWriteoffs', 'Списания баллов', '₽'),
    ('cardChecks', 'Чеки с картой', 'шт'),
    ('nocardChecks', 'Чеки без карты', 'шт'),
    ('cardChecksShare', 'Доля чеков с картой', '%'),
    ('cardRevenue', 'Выручка по картам', '₽'),
    ('tapActivity', 'Активность кранов', '%'),
)

# Сколько изменений в «топе» (блок «Топ-3 изменения» вкладки).
TOP_CHANGES = 3
# Изменение меньше 0,1 % вкладка считает «без изменений» и в топ не берёт.
MIN_TOP_CHANGE_PERCENT = 0.1

FORMULA_TEXT = (
    'Период 1 сравнивается с базой — периодом 2 (как на вкладке «Сравнение»: «было» — '
    'период 2). Δ = период 1 − период 2; Δ% = Δ / период 2 × 100 (база 0 — Δ% нет). '
    'У метрик в процентах Δ — в процентных пунктах. Числа каждого периода — те же, что '
    'карточки «Аналитики» за эти даты. Для списаний баллов рост — хуже (бюджет).'
)


def _number(value) -> float:
    """Число метрики; отсутствующее или нечисловое значение — 0 (как на вкладке)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _fmt(value: float, unit: str) -> str:
    """Число для текста вывода: рубли и штуки целыми с пробелами, проценты с 1 знаком."""
    if unit == '%':
        return ('%.1f' % value).replace('.', ',') + '%'
    return '{:,.0f}'.format(value).replace(',', ' ') + ' ' + unit


class ComparisonCalculator:
    """Сравнение двух периодов по метрикам экрана (правила — в докстринге модуля)."""

    def compare_periods(self, period1: Dict, period2: Dict) -> Dict[str, Dict]:
        """Построчное сравнение.

        Args:
            period1: метрики сравниваемого периода (ключи экрана)
            period2: метрики базы

        Returns:
            {ключ: {label, unit, period1, period2, diff, diff_unit, diff_percent,
                    trend: up|down|stable, budget, better: True|False|None}}
        """
        comparison = {}
        for key, label, unit in COMPARISON_METRICS:
            value1 = _number(period1.get(key))
            value2 = _number(period2.get(key))
            diff = value1 - value2
            diff_percent = round(diff / value2 * 100, 1) if value2 != 0 else None
            budget = key in BUDGET_METRICS
            if diff == 0:
                better = None
            else:
                better = (diff < 0) if budget else (diff > 0)
            comparison[key] = {
                'label': label,
                'unit': unit,
                'period1': value1,
                'period2': value2,
                'diff': round(diff, 2),
                'diff_unit': 'п.п.' if unit == '%' else unit,
                'diff_percent': diff_percent,
                'trend': 'up' if diff > 0 else ('down' if diff < 0 else 'stable'),
                'budget': budget,
                'better': better,
            }
        return comparison

    def top_changes(self, comparison: Dict[str, Dict], top_n: int = TOP_CHANGES) -> List[Dict]:
        """Метрики с наибольшим |Δ%| (правило отбора — в докстринге модуля)."""
        changes = []
        for key, row in comparison.items():
            if row['period1'] == 0 and row['period2'] == 0:
                continue
            if row['diff_percent'] is None or abs(row['diff_percent']) < MIN_TOP_CHANGE_PERCENT:
                continue
            changes.append(dict(row, metric=key))
        changes.sort(key=lambda row: abs(row['diff_percent']), reverse=True)
        return changes[:top_n]

    def insights(self, top: List[Dict]) -> List[str]:
        """Короткие выводы по топу изменений: «Выручка: 1 050 000 ₽ против 1 000 000 ₽ (+5,0%)»."""
        lines = []
        for row in top:
            percent = ('%+.1f' % row['diff_percent']).replace('.', ',') + '%'
            text = (row['label'] + ': ' + _fmt(row['period1'], row['unit']) + ' против '
                    + _fmt(row['period2'], row['unit']) + ' (' + percent + ')')
            if row['better'] is False:
                text += ' — хуже'
            elif row['better'] is True:
                text += ' — лучше'
            lines.append(text)
        return lines

    def summary(self, period1: Dict, period2: Dict) -> Dict:
        """Всё сравнение одним словарём: comparison, top_changes, insights, formula."""
        comparison = self.compare_periods(period1, period2)
        top = self.top_changes(comparison)
        return {
            'comparison': comparison,
            'top_changes': top,
            'insights': self.insights(top),
            'formula': FORMULA_TEXT,
        }

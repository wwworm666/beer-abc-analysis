"""
Менеджер экспорта данных
Экспорт метрик в различные форматы

Выгрузка дашборда в Excel и PDF (POST /api/export/excel, /api/export/pdf) строит
строки одной функцией ExportManager.dashboard_rows — план и факт в ОДНИХ единицах
и по тем же правилам, что карточки «Аналитики» (static/js/dashboard/modules/
analytics.js, buildStats). Правила — в докстринге dashboard_rows.
"""
from typing import Dict, List, Optional
from datetime import datetime
import json

from core.plans_manager import BUDGET_METRICS, plan_score

# Строки выгрузки дашборда: (ключ экрана, подпись, единица). Ключ один для плана и
# факта — как planKey/actualKey в static/js/dashboard/core/config.js. Порядок —
# прежний порядок выгрузки: 16 базовых метрик, четыре метрики лояльности,
# активность кранов последней. У «Чеков с картой», «Чеков без карты» и «Выручки по
# картам» плана нет (на экране это вкладки карточки «Доля чеков с картой»).
DASHBOARD_EXPORT_METRICS = (
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

# План активности кранов, если он не задан (нет плана за период или 0): 100 % —
# правило экрана (analytics.js buildStats: «план всегда 100 %, если не задан вручную»).
TAP_ACTIVITY_DEFAULT_PLAN = 100.0

# Пороги светофора — те же, что на экране (utils.js getStatus): score ≥ 100 —
# выполнено, 90–99 — почти, ниже 90 — не выполнено; score = plan_score (у
# бюджетной метрики — зеркальный процент 200 − p).
STATUS_OK_SCORE = 100.0
STATUS_WARN_SCORE = 90.0


def _as_number(value) -> Optional[float]:
    """Число или None (нечисловое и отсутствующее значение)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class ExportManager:
    """Класс для экспорта данных дашборда"""

    def __init__(self):
        """Инициализация менеджера экспорта"""
        pass

    def dashboard_rows(self, plan: Optional[Dict], fact: Dict) -> List[Dict]:
        """Строки «Метрика | План | Факт | % плана | Разница» выгрузки дашборда.

        Args:
            plan: план за период (plans_manager.calculate_plan_for_period, ключи
                  экрана, проценты — в процентах) или None / {} — плана нет
            fact: факт за период ровно как на экране (routes.dashboard.
                  get_dashboard_analytics_data: наценки уже ×100, tapActivity)

        Правила (зеркало buildStats на экране):
            - план метрики = plan[ключ]; у активности кранов без плана (нет или 0)
              — TAP_ACTIVITY_DEFAULT_PLAN;
            - план есть, если он не None и не 0 (у 0 процент выполнения не определён);
            - % плана = факт / план × 100; разница = факт − план;
            - без плана: plan, percent, diff = None («План не задан» на экране,
              «—» в PDF, пустая ячейка в Excel);
            - status: 'ok' | 'warn' | 'bad' по plan_score (у бюджетной метрики —
              списаний баллов — план служит потолком), 'none' без плана.
            Значения не округляются: округляет печать (Excel — 2 знака).

        Returns:
            [{key, label, unit, plan, fact, percent, diff, budget, score, status}]
            в порядке DASHBOARD_EXPORT_METRICS.
        """
        plan = plan or {}
        rows = []
        for key, label, unit in DASHBOARD_EXPORT_METRICS:
            plan_value = _as_number(plan.get(key))
            if key == 'tapActivity' and not plan_value:
                plan_value = TAP_ACTIVITY_DEFAULT_PLAN
            fact_value = _as_number(fact.get(key)) or 0.0
            has_plan = plan_value is not None and plan_value != 0
            budget = key in BUDGET_METRICS
            if has_plan:
                percent = fact_value / plan_value * 100
                score = plan_score(percent, budget)
                if score >= STATUS_OK_SCORE:
                    status = 'ok'
                elif score >= STATUS_WARN_SCORE:
                    status = 'warn'
                else:
                    status = 'bad'
                diff = fact_value - plan_value
            else:
                plan_value = percent = score = diff = None
                status = 'none'
            rows.append({
                'key': key, 'label': label, 'unit': unit,
                'plan': plan_value, 'fact': fact_value,
                'percent': percent, 'diff': diff,
                'budget': budget, 'score': score, 'status': status,
            })
        return rows

    def prepare_excel_data(
        self,
        venue_name: str,
        period: Dict,
        plan: Dict,
        actual: Dict,
        comparison: Dict
    ) -> Dict:
        """
        Подготовить данные для Excel экспорта

        Args:
            venue_name: str - название заведения
            period: Dict - информация о периоде
            plan: Dict - плановые данные
            actual: Dict - фактические данные
            comparison: Dict - результаты сравнения план/факт

        Returns:
            Dict - структурированные данные для Excel
        """
        # Основная таблица метрик
        metrics_table = []

        metric_names = {
            'revenue': 'Выручка (₽)',
            'checks': 'Чеки (шт)',
            'averageCheck': 'Средний чек (₽)',
            'draftShare': 'Доля розлива (%)',
            'packagedShare': 'Доля фасовки (%)',
            'kitchenShare': 'Доля кухни (%)',
            'revenueDraft': 'Выручка розлив (₽)',
            'revenuePackaged': 'Выручка фасовка (₽)',
            'revenueKitchen': 'Выручка кухня (₽)',
            'markupPercent': '% наценки',
            'profit': 'Прибыль (₽)',
            'markupDraft': 'Наценка розлив (%)',
            'markupPackaged': 'Наценка фасовка (%)',
            'markupKitchen': 'Наценка кухня (%)',
            'loyaltyWriteoffs': 'Списания баллов (₽)',
            # Лояльность (чеки с картой / без карты)
            'cardChecks': 'Чеки с картой (шт)',
            'nocardChecks': 'Чеки без карты (шт)',
            'cardChecksShare': 'Доля чеков с картой (%)',
            'cardRevenue': 'Выручка по картам (₽)'
        }

        for metric_key, metric_name in metric_names.items():
            comp = comparison.get(metric_key, {})

            metrics_table.append({
                'Метрика': metric_name,
                'План': comp.get('period1', 0) if plan else 0,
                'Факт': comp.get('period2', 0) if actual else 0,
                '% плана': f"{(comp.get('period2', 0) / comp.get('period1', 1) * 100):.1f}%" if plan and comp.get('period1', 0) > 0 else 'N/A',
                'Разница': comp.get('diff_abs', 0)
            })

        return {
            'metadata': {
                'venue': venue_name,
                'period_start': period.get('start', ''),
                'period_end': period.get('end', ''),
                'export_date': datetime.now().isoformat()
            },
            'metrics': metrics_table
        }

    def prepare_text_report(
        self,
        venue_name: str,
        period: Dict,
        comparison: Dict,
        insights: List[str]
    ) -> str:
        """
        Подготовить текстовый отчёт для копирования в буфер обмена

        Args:
            venue_name: str - название заведения
            period: Dict - информация о периоде
            comparison: Dict - результаты сравнения
            insights: List[str] - ключевые выводы

        Returns:
            str - форматированный текстовый отчёт
        """
        lines = []

        # Заголовок
        lines.append("=" * 60)
        lines.append("📊 ОТЧЁТ ПО АНАЛИТИКЕ")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Заведение: {venue_name}")
        lines.append(f"Период: {period.get('start', '')} - {period.get('end', '')}")
        lines.append(f"Дата формирования: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append("")

        # Ключевые выводы
        if insights:
            lines.append("-" * 60)
            lines.append("КЛЮЧЕВЫЕ ВЫВОДЫ:")
            lines.append("-" * 60)
            for insight in insights:
                lines.append(f"  {insight}")
            lines.append("")

        # Таблица метрик
        lines.append("-" * 60)
        lines.append("ОСНОВНЫЕ ПОКАЗАТЕЛИ:")
        lines.append("-" * 60)
        lines.append("")

        # Выручка
        revenue = comparison.get('total_revenue', {})
        if revenue:
            lines.append(f"💰 Выручка: {revenue.get('period2', 0):,.0f} ₽")
            lines.append(f"   План: {revenue.get('period1', 0):,.0f} ₽")
            lines.append(f"   Разница: {revenue.get('diff_abs', 0):+,.0f} ₽ ({revenue.get('diff_percent', 0):+.1f}%)")
            lines.append("")

        # Чеки
        checks = comparison.get('total_checks', {})
        if checks:
            lines.append(f"🧾 Чеки: {checks.get('period2', 0):,.0f} шт")
            lines.append(f"   План: {checks.get('period1', 0):,.0f} шт")
            lines.append(f"   Разница: {checks.get('diff_abs', 0):+,.0f} шт ({checks.get('diff_percent', 0):+.1f}%)")
            lines.append("")

        # Средний чек
        avg_check = comparison.get('avg_check', {})
        if avg_check:
            lines.append(f"💵 Средний чек: {avg_check.get('period2', 0):,.0f} ₽")
            lines.append(f"   План: {avg_check.get('period1', 0):,.0f} ₽")
            lines.append(f"   Разница: {avg_check.get('diff_abs', 0):+,.0f} ₽ ({avg_check.get('diff_percent', 0):+.1f}%)")
            lines.append("")

        # Прибыль
        margin = comparison.get('total_margin', {})
        if margin:
            lines.append(f"💹 Прибыль: {margin.get('period2', 0):,.0f} ₽")
            lines.append(f"   План: {margin.get('period1', 0):,.0f} ₽")
            lines.append(f"   Разница: {margin.get('diff_abs', 0):+,.0f} ₽ ({margin.get('diff_percent', 0):+.1f}%)")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def prepare_json_export(
        self,
        venue_key: str,
        venue_name: str,
        period: Dict,
        plan: Dict,
        actual: Dict,
        comparison: Dict
    ) -> str:
        """
        Подготовить JSON для экспорта

        Args:
            venue_key: str - ключ заведения
            venue_name: str - название заведения
            period: Dict - информация о периоде
            plan: Dict - плановые данные
            actual: Dict - фактические данные
            comparison: Dict - результаты сравнения

        Returns:
            str - JSON строка
        """
        export_data = {
            'export_version': '1.0',
            'export_date': datetime.now().isoformat(),
            'venue': {
                'key': venue_key,
                'name': venue_name
            },
            'period': {
                'key': period.get('key', ''),
                'start': period.get('start', ''),
                'end': period.get('end', ''),
                'label': period.get('label', '')
            },
            'plan': plan if plan else {},
            'actual': actual if actual else {},
            'comparison': comparison if comparison else {}
        }

        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def get_filename(
        self,
        venue_name: str,
        period: Dict,
        extension: str
    ) -> str:
        """
        Сгенерировать имя файла для экспорта

        Args:
            venue_name: str - название заведения
            period: Dict - информация о периоде
            extension: str - расширение файла

        Returns:
            str - имя файла
        """
        # Очищаем название от спецсимволов
        clean_venue = venue_name.replace(' - ', '_').replace(' ', '_')
        period_key = period.get('key', 'unknown')

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        return f"dashboard_{clean_venue}_{period_key}_{timestamp}.{extension}"

"""
Менеджер экспорта данных
Экспорт метрик в различные форматы
"""
from typing import Dict, List
from datetime import datetime
import json


class ExportManager:
    """Класс для экспорта данных дашборда"""

    def __init__(self):
        """Инициализация менеджера экспорта"""
        pass

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

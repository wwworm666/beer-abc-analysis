#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт планов из Excel в дашборд
Читает месячные планы и распределяет их на недели пропорционально количеству дней
"""

import pandas as pd
import json
from datetime import datetime
from dashboardNovaev.weeks_generator import WeeksGenerator
from dashboardNovaev.plans_manager import PlansManager

# Маппинг названий баров из Excel на ключи в системе
BAR_MAPPING = {
    'ПЛАН: Кременчугская': 'kremenchugskaya',
    'ПЛАН: Варшавская ': 'varshavskaya',
    'ПЛАН: Лиговский': 'ligovskiy',
    'ПЛАН: ВО': 'bolshoy'
}

# Маппинг месяцев
MONTH_MAPPING = {
    'Ноябрь': 11,
    'Октябрь': 10,
    'Сентябрь': 9
}

def parse_excel_plans(file_path='планы.xlsx'):
    """
    Парсит Excel файл с планами

    Returns:
        dict: {venue_key: {month: {metric: value}}}
    """
    df = pd.read_excel(file_path)

    plans = {}

    # Обрабатываем каждый бар (каждые 3 колонки)
    for col_idx in range(0, len(df.columns), 3):
        bar_name = df.columns[col_idx]

        if bar_name not in BAR_MAPPING:
            continue

        venue_key = BAR_MAPPING[bar_name]

        # Читаем месяц из строки 0
        month_name = df.iloc[0, col_idx]
        if month_name not in MONTH_MAPPING:
            print(f"[WARNING] Неизвестный месяц '{month_name}' для бара {venue_key}")
            continue

        month = MONTH_MAPPING[month_name]
        year = 2025

        # Читаем метрики
        metrics = {}
        for row_idx in range(1, len(df)):
            metric_name = df.iloc[row_idx, col_idx]
            metric_value = df.iloc[row_idx, col_idx + 1]

            if pd.isna(metric_name) or pd.isna(metric_value):
                continue

            # Маппинг метрик из Excel на формат дашборда
            if metric_name == 'Выручка':
                metrics['revenue'] = float(metric_value)
            elif metric_name == 'Прибыль':
                metrics['profit'] = float(metric_value)
            elif metric_name == 'ДОЛЯ Р' or metric_name.startswith('Доля Р'):
                metrics['draftShare'] = float(metric_value)
            elif metric_name == 'Доля Ф' or metric_name.startswith('Доля Ф'):
                metrics['packagedShare'] = float(metric_value)
            elif metric_name == 'Доля К' or metric_name.startswith('Доля К'):
                metrics['kitchenShare'] = float(metric_value)
            elif metric_name == 'Наценка розлив' or metric_name.startswith('Наценка розлив'):
                metrics['markupDraft'] = float(metric_value)
            elif metric_name == 'Наценка фасовка' or metric_name.startswith('Наценка фасовка'):
                metrics['markupPackaged'] = float(metric_value)
            elif metric_name == 'Наценка кухня' or metric_name.startswith('Наценка кухня'):
                metrics['markupKitchen'] = float(metric_value)
            elif metric_name == 'Наценка':
                metrics['markupPercent'] = float(metric_value)
            elif 'кол-во' in metric_name.lower() or 'чеки' in metric_name.lower():
                metrics['checks'] = int(metric_value)
            elif 'средний' in metric_name.lower() and 'чек' in metric_name.lower():
                metrics['averageCheck'] = float(metric_value)

        if venue_key not in plans:
            plans[venue_key] = {}

        plans[venue_key][month] = metrics

        print(f"[OK] Загружено план для {venue_key}, {month_name}: {len(metrics)} метрик")

    return plans

def distribute_to_weeks(plans):
    """
    Распределяет месячные планы на недели пропорционально дням

    Args:
        plans: {venue_key: {month: {metric: value}}}

    Returns:
        dict: {venue_key: {period_key: {metric: value}}}
    """
    weeks_plans = {}

    # Генерируем все недели 2025 года
    weeks = WeeksGenerator.generate_weeks_for_year(2025)

    for venue_key, venue_plans in plans.items():
        weeks_plans[venue_key] = {}

        for month, month_metrics in venue_plans.items():
            # Находим все недели этого месяца
            month_weeks = []
            for week in weeks:
                week_start = datetime.strptime(week['start'], '%Y-%m-%d')
                week_end = datetime.strptime(week['end'], '%Y-%m-%d')

                # Если неделя хотя бы частично в этом месяце
                if week_start.month == month or week_end.month == month:
                    # Считаем сколько дней недели в этом месяце
                    days_in_month = 0
                    from datetime import timedelta
                    for day in range(7):
                        check_date = week_start + timedelta(days=day)
                        if check_date.month == month:
                            days_in_month += 1

                    if days_in_month > 0:
                        month_weeks.append({
                            'week': week,
                            'days_in_month': days_in_month
                        })

            # Распределяем план пропорционально дням
            total_days = sum(w['days_in_month'] for w in month_weeks)

            for week_info in month_weeks:
                week = week_info['week']
                days = week_info['days_in_month']
                proportion = days / total_days

                week_plan = {}
                for metric, value in month_metrics.items():
                    # Доли (shares) и проценты НЕ делятся - они остаются константами
                    if 'Share' in metric or 'Percent' in metric or 'markup' in metric.lower():
                        week_plan[metric] = value
                    else:
                        # Остальные метрики (revenue, checks, profit) делятся пропорционально
                        week_plan[metric] = round(value * proportion, 2)

                weeks_plans[venue_key][week['key']] = week_plan

                print(f"  -> {venue_key} / {week['label']}: {proportion*100:.1f}% месячного плана ({days} дней)")

    return weeks_plans

def save_to_dashboard(weeks_plans, save_all=True):
    """
    Сохраняет планы в формат дашборда для всех баров + общий план

    Args:
        weeks_plans: {venue_key: {period_key: {metric: value}}}
        save_all: Сохранять все бары (True) или только kremenchugskaya (False)
    """
    plans_manager = PlansManager()
    saved_count = 0

    # Собираем все периоды
    all_periods = set()
    for venue_plans in weeks_plans.values():
        all_periods.update(venue_plans.keys())

    # Сохраняем планы для каждого бара
    venues_to_save = weeks_plans.keys() if save_all else ['kremenchugskaya']

    for target_venue in venues_to_save:
        if target_venue not in weeks_plans:
            print(f"[ERROR] Бар {target_venue} не найден в планах")
            continue

        venue_weeks = weeks_plans[target_venue]
        print(f"\nСохранение планов для {target_venue}...")

        for period_key, metrics in venue_weeks.items():
            # Используем составной ключ: venue_period
            composite_key = f"{target_venue}_{period_key}"

            revenue = float(metrics.get('revenue', 0))
            draft_share = float(metrics.get('draftShare', 0))
            packaged_share = float(metrics.get('packagedShare', 0))
            kitchen_share = float(metrics.get('kitchenShare', 0))

            # Вычисляем revenue для каждой категории на основе долей
            revenue_draft = revenue * (draft_share / 100) if draft_share else 0
            revenue_packaged = revenue * (packaged_share / 100) if packaged_share else 0
            revenue_kitchen = revenue * (kitchen_share / 100) if kitchen_share else 0

            # Добавляем недостающие метрики с нулевыми значениями
            full_plan = {
                'revenue': revenue,
                'checks': int(metrics.get('checks', 0)),
                'averageCheck': float(metrics.get('averageCheck', 0)),
                'draftShare': draft_share,
                'packagedShare': packaged_share,
                'kitchenShare': kitchen_share,
                'revenueDraft': revenue_draft,
                'revenuePackaged': revenue_packaged,
                'revenueKitchen': revenue_kitchen,
                'markupPercent': float(metrics.get('markupPercent', 0)),
                'profit': float(metrics.get('profit', 0)),
                'markupDraft': float(metrics.get('markupDraft', 0)),
                'markupPackaged': float(metrics.get('markupPackaged', 0)),
                'markupKitchen': float(metrics.get('markupKitchen', 0)),
                'loyaltyWriteoffs': float(metrics.get('loyaltyWriteoffs', 0))
            }

            success = plans_manager.save_plan(composite_key, full_plan)
            if success:
                saved_count += 1
                print(f"  [OK] {composite_key}")

    # Создаём общие планы (all_) как сумму всех баров
    print(f"\nСоздание общих планов (all)...")
    for period_key in sorted(all_periods):
        total_revenue = 0
        total_checks = 0
        total_profit = 0
        total_revenue_draft = 0
        total_revenue_packaged = 0
        total_revenue_kitchen = 0
        total_loyalty = 0

        # Суммируем по всем барам
        for venue_key in ['kremenchugskaya', 'varshavskaya', 'ligovskiy', 'bolshoy']:
            if venue_key in weeks_plans and period_key in weeks_plans[venue_key]:
                metrics = weeks_plans[venue_key][period_key]
                total_revenue += float(metrics.get('revenue', 0))
                total_checks += int(metrics.get('checks', 0))
                total_profit += float(metrics.get('profit', 0))

                # Revenue по категориям вычисляем через доли
                revenue = float(metrics.get('revenue', 0))
                total_revenue_draft += revenue * (float(metrics.get('draftShare', 0)) / 100)
                total_revenue_packaged += revenue * (float(metrics.get('packagedShare', 0)) / 100)
                total_revenue_kitchen += revenue * (float(metrics.get('kitchenShare', 0)) / 100)

                total_loyalty += float(metrics.get('loyaltyWriteoffs', 0))

        # Пропускаем период если нет данных
        if total_revenue == 0:
            print(f"  [SKIP] {period_key} - нет данных для агрегации")
            continue

        # Вычисляем средний чек и доли
        avg_check = total_revenue / total_checks if total_checks > 0 else 0
        draft_share = (total_revenue_draft / total_revenue * 100) if total_revenue > 0 else 0
        packaged_share = (total_revenue_packaged / total_revenue * 100) if total_revenue > 0 else 0
        kitchen_share = (total_revenue_kitchen / total_revenue * 100) if total_revenue > 0 else 0

        # Вычисляем общую наценку
        markup_percent = (total_profit / (total_revenue - total_profit) * 100) if (total_revenue - total_profit) > 0 else 0

        all_plan = {
            'revenue': total_revenue,
            'checks': total_checks,
            'averageCheck': avg_check,
            'draftShare': draft_share,
            'packagedShare': packaged_share,
            'kitchenShare': kitchen_share,
            'revenueDraft': total_revenue_draft,
            'revenuePackaged': total_revenue_packaged,
            'revenueKitchen': total_revenue_kitchen,
            'markupPercent': markup_percent,
            'profit': total_profit,
            'markupDraft': 0,  # Не суммируем наценки по категориям
            'markupPackaged': 0,
            'markupKitchen': 0,
            'loyaltyWriteoffs': total_loyalty
        }

        all_composite_key = f"all_{period_key}"
        success = plans_manager.save_plan(all_composite_key, all_plan)
        if success:
            saved_count += 1
            print(f"  [OK] {all_composite_key}")

    print(f"\n[OK] Всего сохранено {saved_count} планов")

if __name__ == '__main__':
    print("=" * 60)
    print("ИМПОРТ ПЛАНОВ ИЗ EXCEL В ДАШБОРД")
    print("=" * 60)

    # 1. Парсим Excel
    print("\n1. Чтение планов из Excel...")
    plans = parse_excel_plans()

    # 2. Распределяем на недели
    print("\n2. Распределение планов на недели...")
    weeks_plans = distribute_to_weeks(plans)

    # 3. Сохраняем в дашборд
    print("\n3. Сохранение в дашборд...")
    save_to_dashboard(weeks_plans)

    print("\n" + "=" * 60)
    print("[OK] ИМПОРТ ЗАВЕРШЁН")
    print("=" * 60)

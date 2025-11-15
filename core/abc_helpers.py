"""
Вспомогательные функции для ABC анализа
Убирает дублирование кода в app.py
"""
import pandas as pd


def calculate_abc_category(series, ascending=False):
    """
    Рассчитать ABC категорию для серии значений

    Args:
        series: pandas Series с числовыми значениями
        ascending: True если меньше = лучше

    Returns:
        Series с категориями A, B, C
    """
    if series.empty or series.sum() == 0:
        return pd.Series('C', index=series.index)

    # Сортируем по значению
    sorted_series = series.sort_values(ascending=ascending)

    # Вычисляем накопленный процент
    cumsum = sorted_series.cumsum()
    total = sorted_series.sum()
    cumulative_percent = (cumsum / total) * 100

    # Присваиваем категории
    categories = pd.Series('C', index=series.index)

    # A = первые 80% от суммы
    categories[cumulative_percent <= 80] = 'A'
    # B = следующие 15% (от 80% до 95%)
    categories[(cumulative_percent > 80) & (cumulative_percent <= 95)] = 'B'
    # C = последние 5% (от 95% до 100%)
    categories[cumulative_percent > 95] = 'C'

    return categories


def apply_abc_analysis(df, revenue_col='TotalRevenue', markup_col='AvgMarkupPercent',
                       margin_col='TotalMargin'):
    """
    Применить ABC анализ к DataFrame

    Добавляет колонки:
    - ABC_Revenue (по выручке)
    - ABC_Markup (по % наценки)
    - ABC_Margin (по марже в рублях)
    - ABC_Combined (три буквы вместе, например "ACA")

    Args:
        df: pandas DataFrame
        revenue_col: название колонки с выручкой
        markup_col: название колонки с наценкой %
        margin_col: название колонки с маржей

    Returns:
        DataFrame с добавленными ABC колонками
    """
    result_df = df.copy()

    # Проверяем наличие нужных колонок
    if revenue_col not in result_df.columns:
        raise ValueError(f'Колонка {revenue_col} не найдена в DataFrame')
    if markup_col not in result_df.columns:
        raise ValueError(f'Колонка {markup_col} не найдена в DataFrame')
    if margin_col not in result_df.columns:
        raise ValueError(f'Колонка {margin_col} не найдена в DataFrame')

    # 1-я буква: ABC по выручке (больше = лучше)
    result_df['ABC_Revenue'] = calculate_abc_category(
        result_df[revenue_col],
        ascending=False
    )

    # 2-я буква: ABC по % наценки (больше = лучше)
    result_df['ABC_Markup'] = calculate_abc_category(
        result_df[markup_col],
        ascending=False
    )

    # 3-я буква: ABC по марже в рублях (больше = лучше)
    result_df['ABC_Margin'] = calculate_abc_category(
        result_df[margin_col],
        ascending=False
    )

    # Объединяем три буквы
    result_df['ABC_Combined'] = (
        result_df['ABC_Revenue'] +
        result_df['ABC_Markup'] +
        result_df['ABC_Margin']
    )

    return result_df


def get_abc_stats(df, abc_col='ABC_Combined'):
    """
    Получить статистику по ABC категориям

    Args:
        df: DataFrame с ABC категориями
        abc_col: название колонки с ABC категориями

    Returns:
        dict со статистикой
    """
    if abc_col not in df.columns:
        return {}

    stats = df[abc_col].value_counts().to_dict()
    return stats


def calculate_revenue_percent(df, revenue_col='TotalRevenue'):
    """
    Добавить процент от общей выручки

    Args:
        df: DataFrame
        revenue_col: название колонки с выручкой

    Returns:
        DataFrame с добавленной колонкой RevenuePercent
    """
    result_df = df.copy()

    if revenue_col not in result_df.columns:
        return result_df

    total_revenue = result_df[revenue_col].sum()
    if total_revenue > 0:
        result_df['RevenuePercent'] = (result_df[revenue_col] / total_revenue * 100).round(2)
    else:
        result_df['RevenuePercent'] = 0.0

    return result_df

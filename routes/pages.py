from flask import Blueprint, render_template, redirect
from extensions import BARS, APP_VERSION

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    """Главная страница - Дашборд"""
    return render_template('dashboard.html', bars=BARS)


@pages_bp.route('/packaging')
def packaging():
    """Страница фасовки"""
    return render_template('index.html', bars=BARS)


@pages_bp.route('/draft')
def draft():
    """Страница разливного пива"""
    return render_template('draft.html', bars=BARS)


@pages_bp.route('/waiters')
def waiters():
    """Страница анализа по официантам"""
    return render_template('waiters.html', bars=BARS)


@pages_bp.route('/discounts')
def discounts():
    """Страница анализа скидок"""
    return render_template('discounts.html', bars=BARS)


@pages_bp.route('/taps')
def taps():
    """Главная страница управления кранами - выбор бара"""
    return render_template('taps_main.html')


@pages_bp.route('/stocks')
def stocks():
    """Страница управления стоками и формирования заказов"""
    return render_template('stocks.html', bars=BARS)


@pages_bp.route('/employee')
def employee_dashboard():
    """Страница детального дашборда по сотруднику"""
    return render_template('employee.html', bars=BARS)


@pages_bp.route('/salary')
def salary_page():
    """Страница расчёта ЗП сотрудников (премии + штрафы + KPI + часы)"""
    return render_template('bonus.html')


@pages_bp.route('/bonus')
def bonus_redirect():
    return redirect('/salary')


@pages_bp.route('/kpi')
def kpi_redirect():
    return redirect('/salary')


@pages_bp.route('/dashboard')
def dashboard():
    """Страница аналитического дашборда"""
    return render_template('dashboard.html', bars=BARS, app_version=APP_VERSION)


@pages_bp.route('/taps/<bar_id>')
def taps_bar(bar_id):
    """Страница управления кранами конкретного бара"""
    bars_config = {
        'bar1': {'name': 'Большой пр. В.О', 'taps': 24},
        'bar2': {'name': 'Лиговский', 'taps': 12},
        'bar3': {'name': 'Кременчугская', 'taps': 12},
        'bar4': {'name': 'Варшавская', 'taps': 12}
    }

    if bar_id not in bars_config:
        return "Бар не найден", 404

    bar_info = bars_config[bar_id]
    return render_template('taps_bar.html',
                         bar_id=bar_id,
                         bar_name=bar_info['name'],
                         tap_count=bar_info['taps'])


@pages_bp.route('/schedule')
def schedule():
    """Страница графика смен"""
    return render_template('schedule.html')


@pages_bp.route('/dashboard/widget')
def widget():
    """Страница PWA виджета выручки"""
    return render_template('widget/revenue_widget.html')

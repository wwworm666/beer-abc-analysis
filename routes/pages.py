from flask import Blueprint, redirect, render_template, request
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
    """Анализ проливов: кеги, бармены и баланс склада на одном экране.

    app_version нужен шаблону для кэш-бастинга своих draft.css и draft.js —
    без него правки вёрстки не доезжают до браузеров (docs/lessons.md).
    """
    return render_template('draft.html', bars=BARS, app_version=APP_VERSION)


@pages_bp.route('/waiters')
def waiters_redirect():
    """Анализ по барменам слит в «Анализ проливов» (/draft), вкладка «По барменам».

    Обе страницы жили над одним отчётом iiko по розливу и считали одно и то же, только
    литры по-разному: /draft берёт их из проводок, а /waiters перемножал порции на объём
    из названия блюда. Теперь разрез по людям считается из тех же данных, что и по кегам.
    301 для старых ссылок и закладок — тот же приём, что у /discounts и /schedule/edit.
    """
    return redirect('/draft#bartenders', code=301)


@pages_bp.route('/discounts')
def discounts_redirect():
    """Анализ акций слит в «Маркетинг» (/guests), вкладка «Акции».

    Оставляем 301 для старых ссылок и закладок — тот же приём, что у
    /schedule/edit. Прежний режим RFM жил по ?mode=rfm; RFM-сегментация теперь
    одна и живёт на вкладке #rfm, поэтому старый режим ведём прямо на неё.
    """
    if request.args.get('mode') == 'rfm':
        return redirect('/guests#rfm', code=301)
    return redirect('/guests#promo', code=301)


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


@pages_bp.route('/goals')
def goals_page():
    """Цели месяца — памятка для персонала: план выручки по дням + KPI-цели
    по каждой точке. Собирается из готовых данных (daily_plans + kpi_targets),
    ничего не считает заново. Чтобы в начале месяца скинуть смене её цифры."""
    return render_template('goals.html', app_version=APP_VERSION)


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


@pages_bp.route('/monthly-report')
def monthly_report_page():
    """Отдельная страница «Месячный отчёт» (помесячная динамика метрик за год)"""
    return render_template('monthly_report.html', app_version=APP_VERSION)


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
    """График смен — единая страница: просмотр + редактирование (кисть смен и
    выходных), планы/факты, пожелания, реестр. Прежняя /schedule/edit слита сюда."""
    return render_template('schedule.html', app_version=APP_VERSION)


@pages_bp.route('/schedule/edit')
def schedule_edit():
    """Редактор слит в /schedule — оставляем редирект для старых ссылок/закладок."""
    return redirect('/schedule', code=301)


@pages_bp.route('/dashboard/widget')
def widget():
    """Страница PWA виджета выручки"""
    return render_template('widget/revenue_widget.html')

from .pages import pages_bp
from .analysis import analysis_bp
from .employee import employee_bp
from .taps import taps_bp
from .stocks import stocks_bp
from .dashboard import dashboard_bp
from .schedule import schedule_bp
from .misc import misc_bp
from .menu import menu_bp


def register_blueprints(app):
    app.register_blueprint(pages_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(taps_bp)
    app.register_blueprint(stocks_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(menu_bp)

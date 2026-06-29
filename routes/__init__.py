from .pages import pages_bp
from .analysis import analysis_bp
from .employee import employee_bp
from .taps import taps_bp
from .stocks import stocks_bp
from .dashboard import dashboard_bp
from .schedule import schedule_bp
from .misc import misc_bp
from .expiration import expiration_bp
from .explorer import explorer_bp
from .open_check import open_check_bp
from .menu_editor import menu_editor_bp
from .auth import auth_bp
from .temperature import temperature_bp

# Редактор меню (/menu) перенесён из локального menu_tool/ в основное приложение:
# данные на постоянном диске (/kultura), Chromium для PDF есть в прод-образе
# (mcr.microsoft.com/playwright/python). См. docs/menu-editor.md.


def register_blueprints(app):
    app.register_blueprint(pages_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(taps_bp)
    app.register_blueprint(stocks_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(expiration_bp)
    app.register_blueprint(explorer_bp)
    app.register_blueprint(open_check_bp)
    app.register_blueprint(menu_editor_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(temperature_bp)

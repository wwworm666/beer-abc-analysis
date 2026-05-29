"""Standalone local menu card editor — runs only on the bartender's PC.

Usage:
    cd menu_tool
    py app.py
Then open http://127.0.0.1:5050/menu/library.

NOT deployed to Render. The Playwright/Chromium dependency is heavy and
overflows the 512 MB Render Starter plan during PNG export; running the
tool locally avoids that entirely.
"""

from flask import Flask

from menu_routes import menu_bp


def create_app():
    app = Flask(__name__)
    app.register_blueprint(menu_bp)
    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5050)

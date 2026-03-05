"""Blueprint-Registrierung."""

from .dashboard import dashboard_bp
from .api import api_bp


def register_blueprints(app):
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

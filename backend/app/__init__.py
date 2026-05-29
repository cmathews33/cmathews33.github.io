"""Flask application factory."""
from __future__ import annotations

import os

from flask import Flask
from flask_cors import CORS

from app.api import bp


def create_app() -> Flask:
    app = Flask(__name__)

    # Restrict CORS to the GitHub Pages origin in prod; allow all in dev.
    origins = os.environ.get("CORS_ORIGINS", "*")
    CORS(app, resources={r"/api/*": {"origins": origins.split(",")}})

    app.register_blueprint(bp)
    return app


# Module-level app for `flask --app app run` and the Lambda handler.
app = create_app()

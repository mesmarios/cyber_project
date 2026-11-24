import os

from flask import Flask
from pymysql import MySQLError

from .core.database import close_db, get_db
from .modules.auctions.routes import bp as auctions
from .modules.auth.routes import bp as auth
from .modules.bids.routes import bp as bids
from .modules.profiles.routes import bp as profiles


def create_app():
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
        SESSION_COOKIE_NAME=os.environ.get(
            "FLASK_SESSION_COOKIE_NAME", "student_auctions_session"
        ),
        DB_HOST=os.environ["DB_HOST"],
        DB_PORT=int(os.environ["DB_PORT"]),
        DB_NAME=os.environ["DB_NAME"],
        DB_USER=os.environ["DB_USER"],
        DB_PASSWORD=os.environ["DB_PASSWORD"],
    )

    app.teardown_appcontext(close_db)
    for blueprint in (auth, auctions, bids, profiles):
        app.register_blueprint(blueprint)

    @app.get("/health")
    def health():
        try:
            with get_db().cursor() as cursor:
                cursor.execute("SELECT 1")
        except MySQLError:
            return {"status": "unavailable"}, 503
        return {"status": "ok"}, 200

    return app

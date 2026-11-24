import pymysql
from flask import current_app, g


def get_db():
    if "db" not in g:
        config = current_app.config
        g.db = pymysql.connect(
            host=config["DB_HOST"],
            port=config["DB_PORT"],
            database=config["DB_NAME"],
            user=config["DB_USER"],
            password=config["DB_PASSWORD"],
            charset="utf8mb4",
            init_command="SET time_zone = '+00:00'",
            connect_timeout=3,
            read_timeout=3,
            write_timeout=3,
        )
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()

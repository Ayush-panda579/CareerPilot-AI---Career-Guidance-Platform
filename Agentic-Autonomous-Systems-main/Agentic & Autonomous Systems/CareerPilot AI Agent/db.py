import os
import sqlite3
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


APP_ROOT = Path(__file__).resolve().parent


class DuplicateUserError(Exception):
    """Raised when a username or email address is already registered."""


def _database_url():
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")


def get_conn():
    database_url = _database_url()
    if database_url:
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL is configured, but psycopg is not installed."
            )
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        return psycopg.connect(database_url, row_factory=dict_row)

    if os.getenv("VERCEL") == "1":
        raise RuntimeError(
            "Set DATABASE_URL to a managed PostgreSQL connection string on Vercel."
        )

    sqlite_path = Path(
        os.getenv("SQLITE_PATH", str(APP_ROOT / "careerpilot.db"))
    )
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def _execute(conn, query, parameters=()):
    if _database_url():
        query = query.replace("?", "%s")
    return conn.execute(query, parameters)


def _is_integrity_error(error):
    return isinstance(error, sqlite3.IntegrityError) or (
        psycopg is not None and isinstance(error, psycopg.IntegrityError)
    )


def init_db():
    conn = get_conn()
    try:
        if _database_url():
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
                """,
            )
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS contact_messages (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
        else:
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
                """,
            )
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS contact_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
        conn.commit()
    finally:
        conn.close()


def create_user(username, email, password):
    conn = get_conn()
    try:
        _execute(
            conn,
            """
            INSERT INTO users (username, email, password)
            VALUES (?, ?, ?)
            """,
            (username, email, password),
        )
        conn.commit()
    except Exception as error:
        if _is_integrity_error(error):
            raise DuplicateUserError(
                "Username or email address is already registered."
            ) from error
        raise
    finally:
        conn.close()


def get_user(username):
    conn = get_conn()
    try:
        return _execute(
            conn,
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
    finally:
        conn.close()


def create_contact_message(name, email, message):
    conn = get_conn()
    try:
        _execute(
            conn,
            """
            INSERT INTO contact_messages (name, email, message)
            VALUES (?, ?, ?)
            """,
            (name, email, message),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")

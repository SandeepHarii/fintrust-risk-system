import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extensions import connection


def get_database_connection() -> connection:
    """
    Create and return a PostgreSQL database connection.

    Configuration is read from environment variables so credentials
    are not hardcoded into the application.
    """
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=10,
        sslmode=os.getenv("DB_SSLMODE", "require"),
    )


@contextmanager
def get_db_connection():
    """
    Provide a database connection with automatic commit/rollback handling.

    Commits when the operation completes successfully.
    Rolls back when an exception occurs.
    Always closes the connection afterwards.
    """
    conn = get_database_connection()

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
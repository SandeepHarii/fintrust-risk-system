import pytest

from fintrust.db import get_db_connection


def test_database_connection():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()

    assert result == (1,)


def test_database_rollback():
    with pytest.raises(RuntimeError):
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "CREATE TEMP TABLE rollback_test (id INTEGER);"
                )
                cursor.execute(
                    "INSERT INTO rollback_test VALUES (1);"
                )
                raise RuntimeError("Intentional rollback test")
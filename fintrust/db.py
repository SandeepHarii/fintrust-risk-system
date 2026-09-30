import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extensions import connection

from fintrust.config import get_config


def get_database_connection() -> connection:
    return psycopg2.connect(
        host=get_config("DB_HOST"),
        port=int(get_config("DB_PORT", "5432")),
        database=get_config("DB_NAME"),
        user=get_config("DB_USER"),
        password=get_config("DB_PASSWORD", decrypt=True),
        connect_timeout=10,
        sslmode=get_config("DB_SSLMODE", "require"),
    )


@contextmanager
def get_db_connection():
    conn = get_database_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_transaction(
    conn: connection,
    transaction: dict,
    risk_flag: str,
) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO transactions (
                transaction_id,
                account_id,
                tx_date,
                amount,
                currency,
                transaction_type,
                source_country,
                destination_country,
                risk_flag
            )
            VALUES (
                %(transaction_id)s,
                %(account_id)s,
                %(tx_date)s,
                %(amount)s,
                %(currency)s,
                %(transaction_type)s,
                %(source_country)s,
                %(destination_country)s,
                %(risk_flag)s
            )
            """,
            {
                "transaction_id": transaction["transaction_id"],
                "account_id": transaction["account_id"],
                "tx_date": transaction["tx_date"],
                "amount": transaction["amount"],
                "currency": transaction["currency"],
                "transaction_type": transaction["transaction_type"],
                "source_country": transaction["source_country"],
                "destination_country": transaction["destination_country"],
                "risk_flag": risk_flag,
            },
        )
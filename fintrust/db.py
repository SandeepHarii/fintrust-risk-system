import os
import uuid
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


def flag_transaction(
    conn: connection,
    transaction_id: str,
    reason: str,
) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                account_id
            FROM transactions
            WHERE transaction_id = %s
            """,
            (transaction_id,),
        )

        transaction = cursor.fetchone()

        if transaction is None:
            raise ValueError("Transaction not found.")

        account_id = transaction[0]

        cursor.execute(
            """
            UPDATE transactions
            SET risk_flag = 'HIGH'
            WHERE transaction_id = %s
            """,
            (transaction_id,),
        )

        risk_event_id = uuid.uuid4()
        alert_id = uuid.uuid4()

        cursor.execute(
            """
            INSERT INTO risk_events (
                risk_event_id,
                account_id,
                transaction_id,
                reason,
                risk_level
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                'HIGH'
            )
            """,
            (
                str(risk_event_id),
                account_id,
                transaction_id,
                reason,
            ),
        )

        cursor.execute(
            """
            INSERT INTO alerts (
                alert_id,
                account_id,
                transaction_id,
                risk_event_id,
                alert_status
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                'PENDING'
            )
            """,
            (
                str(alert_id),
                account_id,
                transaction_id,
                str(risk_event_id),
            ),
        )

    return {
        "alert_id": str(alert_id),
        "risk_event_id": str(risk_event_id),
        "account_id": str(account_id),
        "transaction_id": transaction_id,
        "reason": reason,
        "risk_level": "HIGH",
        "alert_status": "PENDING",
    }


def get_alert(
    conn: connection,
    alert_id: str,
) -> dict | None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                alert_id,
                account_id,
                transaction_id,
                risk_event_id,
                alert_status,
                sent_at,
                resolved_at
            FROM alerts
            WHERE alert_id = %s
            """,
            (alert_id,),
        )

        row = cursor.fetchone()

    if row is None:
        return None

    return {
        "alert_id": str(row[0]),
        "account_id": str(row[1]),
        "transaction_id": str(row[2]),
        "risk_event_id": str(row[3]),
        "alert_status": row[4],
        "sent_at": row[5].isoformat() if row[5] else None,
        "resolved_at": row[6].isoformat() if row[6] else None,
    }


def mark_alert_sent(
    conn: connection,
    alert_id: str,
) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE alerts
            SET
                alert_status = 'SENT',
                sent_at = CURRENT_TIMESTAMP
            WHERE alert_id = %s
              AND alert_status = 'PENDING'
            RETURNING
                alert_id,
                account_id,
                transaction_id,
                risk_event_id,
                alert_status,
                sent_at,
                resolved_at
            """,
            (alert_id,),
        )

        row = cursor.fetchone()

    if row is None:
        raise ValueError(
            "Alert not found or alert is not in PENDING status."
        )

    return {
        "alert_id": str(row[0]),
        "account_id": str(row[1]),
        "transaction_id": str(row[2]),
        "risk_event_id": str(row[3]),
        "alert_status": row[4],
        "sent_at": row[5].isoformat() if row[5] else None,
        "resolved_at": row[6].isoformat() if row[6] else None,
    }


def mark_alert_failed(
    conn: connection,
    alert_id: str,
) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE alerts
            SET
                alert_status = 'FAILED'
            WHERE alert_id = %s
              AND alert_status = 'PENDING'
            RETURNING
                alert_id,
                account_id,
                transaction_id,
                risk_event_id,
                alert_status,
                sent_at,
                resolved_at
            """,
            (alert_id,),
        )

        row = cursor.fetchone()

    if row is None:
        raise ValueError(
            "Alert not found or alert is not in PENDING status."
        )

    return {
        "alert_id": str(row[0]),
        "account_id": str(row[1]),
        "transaction_id": str(row[2]),
        "risk_event_id": str(row[3]),
        "alert_status": row[4],
        "sent_at": row[5].isoformat() if row[5] else None,
        "resolved_at": row[6].isoformat() if row[6] else None,
    }


def resolve_alert(
    conn: connection,
    alert_id: str,
) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE alerts
            SET
                alert_status = 'RESOLVED',
                resolved_at = CURRENT_TIMESTAMP
            WHERE alert_id = %s
              AND alert_status = 'SENT'
            RETURNING
                alert_id,
                account_id,
                transaction_id,
                risk_event_id,
                alert_status,
                sent_at,
                resolved_at
            """,
            (alert_id,),
        )

        row = cursor.fetchone()

    if row is None:
        raise ValueError(
            "Alert not found or alert is not in SENT status."
        )

    return {
        "alert_id": str(row[0]),
        "account_id": str(row[1]),
        "transaction_id": str(row[2]),
        "risk_event_id": str(row[3]),
        "alert_status": row[4],
        "sent_at": row[5].isoformat() if row[5] else None,
        "resolved_at": row[6].isoformat() if row[6] else None,
    }
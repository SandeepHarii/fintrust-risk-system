from typing import Any

from fintrust.db import get_db_connection


def get_transactions(
    account_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    if page < 1:
        raise ValueError("page must be greater than or equal to 1.")

    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100.")

    offset = (page - 1) * page_size

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            count_query = """
                SELECT COUNT(*)
                FROM transactions
            """

            count_params: tuple[str, ...] = ()

            if account_id:
                count_query += """
                    WHERE account_id = %s
                """
                count_params = (account_id,)

            cursor.execute(count_query, count_params)
            total = cursor.fetchone()[0]

            transaction_query = """
                SELECT
                    transaction_id,
                    account_id,
                    tx_date,
                    amount,
                    currency,
                    transaction_type,
                    source_country,
                    destination_country,
                    risk_flag,
                    created_at
                FROM transactions
            """

            transaction_params: tuple[Any, ...] = ()

            if account_id:
                transaction_query += """
                    WHERE account_id = %s
                """
                transaction_params = (account_id,)

            transaction_query += """
                ORDER BY tx_date DESC
                LIMIT %s
                OFFSET %s
            """

            transaction_params += (page_size, offset)

            cursor.execute(transaction_query, transaction_params)
            rows = cursor.fetchall()

    transactions = [
        {
            "transaction_id": str(row[0]),
            "account_id": str(row[1]),
            "tx_date": row[2].isoformat(),
            "amount": str(row[3]),
            "currency": row[4].strip(),
            "transaction_type": row[5],
            "source_country": row[6].strip(),
            "destination_country": row[7].strip(),
            "risk_flag": row[8],
            "created_at": row[9].isoformat(),
        }
        for row in rows
    ]

    return {
        "transactions": transactions,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


def get_insights() -> dict[str, Any]:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_transactions,
                    COUNT(*) FILTER (
                        WHERE risk_flag = 'LOW'
                    ) AS low_transactions,
                    COUNT(*) FILTER (
                        WHERE risk_flag = 'MEDIUM'
                    ) AS medium_transactions,
                    COUNT(*) FILTER (
                        WHERE risk_flag = 'HIGH'
                    ) AS high_transactions
                FROM transactions
                """
            )

            transaction_summary = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM risk_events
                """
            )

            total_risk_events = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_alerts,
                    COUNT(*) FILTER (
                        WHERE alert_status = 'PENDING'
                    ) AS pending_alerts,
                    COUNT(*) FILTER (
                        WHERE alert_status = 'SENT'
                    ) AS sent_alerts,
                    COUNT(*) FILTER (
                        WHERE alert_status = 'RESOLVED'
                    ) AS resolved_alerts,
                    COUNT(*) FILTER (
                        WHERE alert_status = 'FAILED'
                    ) AS failed_alerts
                FROM alerts
                """
            )

            alert_summary = cursor.fetchone()

    return {
        "transactions": {
            "total": transaction_summary[0],
            "low": transaction_summary[1],
            "medium": transaction_summary[2],
            "high": transaction_summary[3],
        },
        "risk_events": {
            "total": total_risk_events,
        },
        "alerts": {
            "total": alert_summary[0],
            "pending": alert_summary[1],
            "sent": alert_summary[2],
            "resolved": alert_summary[3],
            "failed": alert_summary[4],
        },
    }
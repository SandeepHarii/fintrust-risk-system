
from typing import Any

from fintrust.db import get_db_connection


def get_transactions(
    account_id: str | None = None,
    page: int = 1,
    page_size: int = 5,
    search: str | None = None,
    risk_filter: str | None = None,
    flag_filter: str | None = None,
) -> dict[str, Any]:

    if page < 1:
        raise ValueError("page must be greater than or equal to 1.")

    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100.")

    if risk_filter:
        risk_filter = risk_filter.strip().upper()

    if flag_filter:
        flag_filter = flag_filter.strip().upper()

    if risk_filter and risk_filter not in ("LOW", "MEDIUM", "HIGH"):
        raise ValueError("risk_filter must be LOW, MEDIUM or HIGH.")

    offset = (page - 1) * page_size

    conditions = []
    params: list[Any] = []

    if account_id:
        conditions.append("t.account_id = %s")
        params.append(account_id)

    if risk_filter:
        conditions.append("t.risk_flag = %s")
        params.append(risk_filter)

    # Match individual reasons, even when multiple reasons
    # are stored together in a comma-separated string.
    if flag_filter:
        conditions.append("""
            EXISTS (
                SELECT 1
                FROM risk_events re
                CROSS JOIN LATERAL
                    unnest(string_to_array(re.reason, ',')) AS parts(reason_part)
                WHERE re.transaction_id = t.transaction_id
                  AND UPPER(BTRIM(parts.reason_part)) = %s
            )
        """)
        params.append(flag_filter)

    
    if search and search.strip():
        search_value = search.strip()
        search_term = f"%{search_value}%"

        # Normalise the input and formatted dates to support
        # searches with or without spaces and punctuation.
        compact_search = "".join(
            character
            for character in search_value.lower()
            if character.isalnum()
        )
        compact_term = f"%{compact_search}%"

        conditions.append("""
            (
                -- Search every column in the transaction record.
                to_jsonb(t)::TEXT ILIKE %s

                -- Search every column in associated risk events.
                OR EXISTS (
                    SELECT 1
                    FROM risk_events re
                    WHERE re.transaction_id = t.transaction_id
                      AND to_jsonb(re)::TEXT ILIKE %s
                )

                -- Search transaction dates in common formats.
                OR TO_CHAR(t.tx_date, 'DD Mon YYYY') ILIKE %s
                OR TO_CHAR(t.tx_date, 'FMDD Month YYYY') ILIKE %s
                OR TO_CHAR(t.tx_date, 'DD/MM/YYYY') ILIKE %s
                OR TO_CHAR(t.tx_date, 'DD-MM-YYYY') ILIKE %s

                -- Also support date searches without spaces
                -- or punctuation, such as 11oct.
                OR REGEXP_REPLACE(
                    LOWER(TO_CHAR(t.tx_date, 'DD Mon YYYY')),
                    '[^a-z0-9]', '', 'g'
                ) ILIKE %s

                OR REGEXP_REPLACE(
                    LOWER(TO_CHAR(t.tx_date, 'FMDD Month YYYY')),
                    '[^a-z0-9]', '', 'g'
                ) ILIKE %s
            )
        """)

        params.extend(
            [search_term] * 6 + [compact_term] * 2
        )

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            # Count all transactions matching the selected filters.
            count_query = f"""
                SELECT COUNT(*)
                FROM transactions t
                {where_clause}
            """

            cursor.execute(count_query, tuple(params))
            total = cursor.fetchone()[0]

            # Retrieve only the requested page of matching transactions.
            transaction_query = f"""
                SELECT
                    t.transaction_id,
                    t.account_id,
                    t.tx_date,
                    t.amount,
                    t.currency,
                    t.transaction_type,
                    t.source_country,
                    t.destination_country,
                    t.risk_flag,
                    t.created_at,

                    COALESCE(
                        (
                            SELECT ARRAY_AGG(
                                DISTINCT BTRIM(parts.reason_part)::VARCHAR
                            )
                            FROM risk_events re
                            CROSS JOIN LATERAL
                                unnest(string_to_array(re.reason, ',')) AS parts(reason_part)
                            WHERE re.transaction_id = t.transaction_id
                              AND UPPER(BTRIM(parts.reason_part)) <> 'NONE'
                        ),
                        ARRAY[]::VARCHAR[]
                    ) AS flags

                FROM transactions t

                {where_clause}

                ORDER BY t.tx_date DESC, t.transaction_id DESC

                LIMIT %s
                OFFSET %s
            """

            transaction_params = params + [page_size, offset]

            cursor.execute(
                transaction_query,
                tuple(transaction_params),
            )

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
            "flags": row[10] or [],
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
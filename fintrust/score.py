import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

from fintrust.db import get_db_connection
from fintrust.dynamo import put_risk_event


logger = logging.getLogger()
logger.setLevel(logging.INFO)


HIGH_AMOUNT_POINTS = 30
HIGH_VELOCITY_POINTS = 40
CROSS_BORDER_POINTS = 20
MEDIUM_THRESHOLD = 30
HIGH_THRESHOLD = 60

ALERT_LAMBDA_NAME = os.getenv(
    "ALERT_LAMBDA_NAME",
    "fintrust-prod-alert",
)

_lambda = boto3.client("lambda", region_name="eu-north-1")


def calculate_risk_score(
    transaction: dict[str, Any],
    account_transactions: list[dict[str, Any]],
) -> tuple[int, str, list[str]]:
    """Calculate the final risk score and classification."""
    score = 0
    reasons: list[str] = []

    try:
        amount = float(transaction["amount"])
    except (KeyError, TypeError, ValueError):
        return 0, "LOW", ["INVALID_AMOUNT"]

    if amount > 50000:
        score += HIGH_AMOUNT_POINTS
        reasons.append("HIGH_AMOUNT")

    source_country = str(
        transaction["source_country"]
    ).strip().upper()

    destination_country = str(
        transaction["destination_country"]
    ).strip().upper()

    if source_country != destination_country:
        score += CROSS_BORDER_POINTS
        reasons.append("CROSS_BORDER")

    transaction_time = datetime.fromisoformat(
        str(transaction["tx_date"]).replace("Z", "+00:00")
    )

    # Normalise timestamps so comparisons work with both
    # timezone-aware and timezone-naive database/test values.
    if transaction_time.tzinfo is None:
        transaction_time = transaction_time.replace(
            tzinfo=timezone.utc
        )

    window_start = transaction_time - timedelta(hours=1)
    velocity_count = 0

    for account_transaction in account_transactions:
        try:
            other_time = datetime.fromisoformat(
                str(account_transaction["tx_date"]).replace(
                    "Z", "+00:00"
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "Skipping transaction with an invalid timestamp"
            )
            continue

        if other_time.tzinfo is None:
            other_time = other_time.replace(
                tzinfo=timezone.utc
            )

        if window_start <= other_time <= transaction_time:
            velocity_count += 1

    if velocity_count > 10:
        score += HIGH_VELOCITY_POINTS
        reasons.append("HIGH_VELOCITY")

    # Mandatory high-risk rules take priority over the
    # weighted score thresholds.
    if (
        "HIGH_AMOUNT" in reasons
        or "HIGH_VELOCITY" in reasons
        or score >= HIGH_THRESHOLD
    ):
        risk_level = "HIGH"
    elif score >= MEDIUM_THRESHOLD:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return score, risk_level, reasons


def get_account_transactions(
    conn: Any,
    account_id: str,
) -> list[dict[str, Any]]:
    """Retrieve an account's transactions for velocity analysis."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                transaction_id,
                account_id,
                tx_date
            FROM transactions
            WHERE account_id = %s
            ORDER BY tx_date
            """,
            (account_id,),
        )

        rows = cursor.fetchall()

    return [
        {
            "transaction_id": str(row[0]),
            "account_id": str(row[1]),
            "tx_date": row[2].isoformat(),
        }
        for row in rows
    ]


def update_transaction_risk(
    conn: Any,
    transaction_id: str,
    risk_level: str,
) -> None:
    """Update the transaction's final risk classification."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE transactions
            SET risk_flag = %s
            WHERE transaction_id = %s
            """,
            (risk_level, transaction_id),
        )

        if cursor.rowcount != 1:
            raise ValueError(
                f"Transaction not found: {transaction_id}"
            )


def insert_postgres_risk_event(
    conn: Any,
    transaction: dict[str, Any],
    risk_level: str,
    risk_reasons: list[str],
) -> str:
    """Insert the final risk event into PostgreSQL."""
    risk_event_id = str(uuid.uuid4())

    reason = (
        ",".join(risk_reasons)
        if risk_reasons
        else "NONE"
    )

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO risk_events (
                risk_event_id,
                account_id,
                transaction_id,
                reason,
                risk_level
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                risk_event_id,
                transaction["account_id"],
                transaction["transaction_id"],
                reason,
                risk_level,
            ),
        )

    return risk_event_id


def create_alert(
    conn: Any,
    transaction: dict[str, Any],
    risk_event_id: str,
) -> str:
    """Create a pending compliance alert."""
    alert_id = str(uuid.uuid4())

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO alerts (
                alert_id,
                account_id,
                transaction_id,
                risk_event_id,
                alert_status
            )
            VALUES (%s, %s, %s, %s, 'PENDING')
            """,
            (
                alert_id,
                transaction["account_id"],
                transaction["transaction_id"],
                risk_event_id,
            ),
        )

    return alert_id


def update_alert_status(
    conn: Any,
    alert_id: str,
    status: str,
) -> None:
    """Update alert status and timestamps."""
    if status == "SENT":
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE alerts
                SET
                    alert_status = 'SENT',
                    sent_at = %s
                WHERE alert_id = %s
                """,
                (
                    datetime.now(timezone.utc),
                    alert_id,
                ),
            )

    elif status == "FAILED":
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE alerts
                SET alert_status = 'FAILED'
                WHERE alert_id = %s
                """,
                (alert_id,),
            )

    else:
        raise ValueError(
            f"Unsupported alert status: {status}"
        )


def invoke_alert_lambda(
    alert_id: str,
    transaction: dict[str, Any],
    risk_event_id: str,
    risk_level: str,
    risk_reasons: list[str],
) -> None:
    """Invoke the compliance alert Lambda."""
    payload = {
        "alert_id": alert_id,
        "transaction_id": str(transaction["transaction_id"]),
        "account_id": str(transaction["account_id"]),
        "risk_event_id": risk_event_id,
        "risk_level": risk_level,
        "reason": (
            ",".join(risk_reasons)
            if risk_reasons
            else "NONE"
        ),
    }

    response = _lambda.invoke(
        FunctionName=ALERT_LAMBDA_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    if response.get("FunctionError"):
        raise RuntimeError(
            f"Alert Lambda failed: {response['FunctionError']}"
        )

    response_payload = response.get("Payload")

    if response_payload is not None:
        raw_response = response_payload.read()

        if raw_response:
            alert_response = json.loads(raw_response)

            if alert_response.get("statusCode", 200) >= 400:
                raise RuntimeError(
                    f"Alert Lambda returned an error: "
                    f"{alert_response}"
                )

    logger.info(
        json.dumps(
            {
                "event": "alert_lambda_invoked",
                "alert_id": alert_id,
                "transaction_id": transaction["transaction_id"],
            },
            default=str,
        )
    )


def process_transaction(
    transaction: dict[str, Any],
) -> dict[str, Any]:
    """Calculate and persist the final risk result."""
    alert_id = None

    with get_db_connection() as conn:
        account_transactions = get_account_transactions(
            conn=conn,
            account_id=str(transaction["account_id"]),
        )

        risk_score, risk_level, risk_reasons = calculate_risk_score(
            transaction=transaction,
            account_transactions=account_transactions,
        )

        update_transaction_risk(
            conn=conn,
            transaction_id=str(transaction["transaction_id"]),
            risk_level=risk_level,
        )

        risk_event_id = insert_postgres_risk_event(
            conn=conn,
            transaction=transaction,
            risk_level=risk_level,
            risk_reasons=risk_reasons,
        )

        if risk_level == "HIGH":
            alert_id = create_alert(
                conn=conn,
                transaction=transaction,
                risk_event_id=risk_event_id,
            )

    put_risk_event(
        account_id=str(transaction["account_id"]),
        transaction_timestamp=str(transaction["tx_date"]),
        risk_event={
            "transaction_id": str(transaction["transaction_id"]),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
        },
    )

    if risk_level == "HIGH" and alert_id:
        try:
            invoke_alert_lambda(
                alert_id=alert_id,
                transaction=transaction,
                risk_event_id=risk_event_id,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
            )

            with get_db_connection() as conn:
                update_alert_status(
                    conn=conn,
                    alert_id=alert_id,
                    status="SENT",
                )

        except Exception:
            logger.exception(
                json.dumps(
                    {
                        "event": "alert_processing_failed",
                        "alert_id": alert_id,
                        "transaction_id": transaction["transaction_id"],
                    },
                    default=str,
                )
            )

            with get_db_connection() as conn:
                update_alert_status(
                    conn=conn,
                    alert_id=alert_id,
                    status="FAILED",
                )

            raise

    result = {
        "transaction_id": str(transaction["transaction_id"]),
        "account_id": str(transaction["account_id"]),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "risk_event_id": risk_event_id,
    }

    if alert_id:
        result["alert_id"] = alert_id

    logger.info(
        json.dumps(
            {
                "event": "transaction_scored",
                **result,
            },
            default=str,
        )
    )

    return result


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Process transactions received from SQS FIFO."""
    processed = 0
    results: list[dict[str, Any]] = []

    logger.info(
        json.dumps(
            {
                "event": "score_lambda_invoked",
                "record_count": len(event.get("Records", [])),
                "request_id": getattr(
                    context,
                    "aws_request_id",
                    None,
                ),
            },
            default=str,
        )
    )

    for record in event.get("Records", []):
        message = json.loads(record["body"])
        transaction = message["transaction"]

        result = process_transaction(
            transaction=transaction,
        )

        results.append(result)
        processed += 1

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Transactions scored successfully",
                "processed": processed,
                "results": results,
            },
            default=str,
        ),
    }
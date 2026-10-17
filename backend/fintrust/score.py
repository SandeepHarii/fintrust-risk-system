
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import boto3

from fintrust.db import get_db_connection
from fintrust.dynamo import (
    mark_transaction_persisted,
    mark_transaction_scored,
    put_risk_event,
)


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


def insert_transaction_if_missing(
    conn: Any,
    transaction: dict[str, Any],
) -> bool:
    """
    Insert a transaction or verify an existing transaction is identical.

    Returns:
        True: A new transaction was inserted.
        False: The transaction already existed with identical details.

    Raises:
        ValueError: If the transaction ID exists with different details.
    """
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
                destination_country
            )
            VALUES (
                %(transaction_id)s,
                %(account_id)s,
                %(tx_date)s,
                %(amount)s,
                %(currency)s,
                %(transaction_type)s,
                %(source_country)s,
                %(destination_country)s
            )
            ON CONFLICT (transaction_id) DO NOTHING
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
            },
        )

        # Capture rowcount before executing the SELECT.
        inserted = cursor.rowcount == 1

        cursor.execute(
            """
            SELECT
                account_id,
                tx_date,
                amount,
                currency,
                transaction_type,
                source_country,
                destination_country
            FROM transactions
            WHERE transaction_id = %s
            """,
            (transaction["transaction_id"],),
        )

        existing = cursor.fetchone()

    if existing is None:
        raise ValueError(
            f"Transaction insertion failed: "
            f"{transaction['transaction_id']}"
        )

    existing_timestamp = existing[1]

    incoming_timestamp = datetime.fromisoformat(
        str(transaction["tx_date"]).replace("Z", "+00:00")
    )

    if existing_timestamp.tzinfo is None:
        existing_timestamp = existing_timestamp.replace(
            tzinfo=timezone.utc
        )

    if incoming_timestamp.tzinfo is None:
        incoming_timestamp = incoming_timestamp.replace(
            tzinfo=timezone.utc
        )

    existing_details = {
        "account_id": str(existing[0]),
        "tx_date": existing_timestamp.astimezone(timezone.utc),
        "amount": Decimal(str(existing[2])).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        ),
        "currency": str(existing[3]).strip(),
        "transaction_type": str(existing[4]),
        "source_country": str(existing[5]).strip(),
        "destination_country": str(existing[6]).strip(),
    }

    incoming_details = {
        "account_id": str(transaction["account_id"]),
        "tx_date": incoming_timestamp.astimezone(timezone.utc),
        "amount": Decimal(str(transaction["amount"])).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        ),
        "currency": str(transaction["currency"]).strip(),
        "transaction_type": str(transaction["transaction_type"]),
        "source_country": str(transaction["source_country"]).strip(),
        "destination_country": str(transaction["destination_country"]).strip(),
    }

    if existing_details != incoming_details:
        raise ValueError(
            "Transaction ID already exists with different transaction details: "
            f"{transaction['transaction_id']}"
        )

    return inserted


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


def get_existing_risk_event(
    conn: Any,
    transaction_id: str,
) -> dict[str, Any] | None:
    """Retrieve an existing risk event and associated alert."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                re.risk_event_id,
                re.reason,
                re.risk_level,
                a.alert_id,
                a.alert_status
            FROM risk_events re
            LEFT JOIN alerts a
                ON a.risk_event_id = re.risk_event_id
            WHERE re.transaction_id = %s
            ORDER BY re.created_at DESC
            LIMIT 1
            """,
            (transaction_id,),
        )

        row = cursor.fetchone()

    if row is None:
        return None

    return {
        "risk_event_id": str(row[0]),
        "risk_reasons": (
            []
            if row[1] == "NONE"
            else row[1].split(",")
        ),
        "risk_level": row[2],
        "alert_id": str(row[3]) if row[3] else None,
        "alert_status": row[4],
    }


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
    upload_id: str | None = None,
) -> dict[str, Any]:
    """Insert, score and persist a transaction idempotently."""
    alert_id = None
    alert_status = None

    transaction_id = str(transaction["transaction_id"])
    account_id = str(transaction["account_id"])

    with get_db_connection() as conn:
        is_new_transaction = insert_transaction_if_missing(
            conn=conn,
            transaction=transaction,
        )

        # Check for an existing risk event before doing any scoring work.
        existing_event = get_existing_risk_event(
            conn=conn,
            transaction_id=transaction_id,
        )

        if existing_event:
            # Reuse the existing risk decision.
            risk_event_id = existing_event["risk_event_id"]
            risk_level = existing_event["risk_level"]
            risk_reasons = existing_event["risk_reasons"]
            alert_id = existing_event["alert_id"]
            alert_status = existing_event["alert_status"]

            # Reconstruct the original score from persisted reasons.
            points = {
                "HIGH_AMOUNT": HIGH_AMOUNT_POINTS,
                "HIGH_VELOCITY": HIGH_VELOCITY_POINTS,
                "CROSS_BORDER": CROSS_BORDER_POINTS,
            }

            risk_score = sum(
                points.get(reason, 0)
                for reason in risk_reasons
            )

            logger.info(
                json.dumps(
                    {
                        "event": "existing_risk_event_reused",
                        "transaction_id": transaction_id,
                        "risk_event_id": risk_event_id,
                        "duplicate_transaction": not is_new_transaction,
                    },
                    default=str,
                )
            )

        else:
            # No risk event exists, so calculate the score.
            # This also handles recovery after a partially completed attempt.
            account_transactions = get_account_transactions(
                conn=conn,
                account_id=account_id,
            )

            risk_score, risk_level, risk_reasons = (
                calculate_risk_score(
                    transaction=transaction,
                    account_transactions=account_transactions,
                )
            )

            risk_event_id = None

        # Record scoring independently of persistence.
        # This remains upload-specific, including for duplicates.
        if upload_id:
            mark_transaction_scored(
                upload_id=upload_id,
                transaction_id=transaction_id,
                duplicate_transaction=not is_new_transaction,
            )

        if existing_event:
            # Recover an alert if an earlier attempt created the
            # risk event but did not create its alert.
            if risk_level == "HIGH" and not alert_id:
                alert_id = create_alert(
                    conn=conn,
                    transaction=transaction,
                    risk_event_id=risk_event_id,
                )
                alert_status = "PENDING"

        else:
            update_transaction_risk(
                conn=conn,
                transaction_id=transaction_id,
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
                alert_status = "PENDING"

        update_transaction_risk(
            conn=conn,
            transaction_id=transaction_id,
            risk_level=risk_level,
        )

    # Persist the risk event to DynamoDB after PostgreSQL commits.
    # This also repairs DynamoDB if a previous attempt failed after
    # committing the PostgreSQL transaction.
    put_risk_event(
        account_id=account_id,
        transaction_id=transaction_id,
        transaction_timestamp=str(transaction["tx_date"]),
        risk_event={
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
        },
    )

    # Persistence is complete only after both database writes succeed.
    # Duplicate transactions still need their own upload tracking markers.
    if upload_id:
        mark_transaction_persisted(
            upload_id=upload_id,
            transaction_id=transaction_id,
        )

    # Alert delivery is separate from the persistence milestone.
    # Never resend an alert already marked SENT or RESOLVED.
    if (
        risk_level == "HIGH"
        and alert_id
        and alert_status not in {"SENT", "RESOLVED"}
    ):
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
                        "transaction_id": transaction_id,
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
        "transaction_id": transaction_id,
        "account_id": account_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "risk_event_id": risk_event_id,
        "duplicate_transaction": not is_new_transaction,
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
            }
        )
    )

    for record in event.get("Records", []):
        message = json.loads(record["body"])
        transaction = message["transaction"]
        upload_id = message.get("upload_id")

        result = process_transaction(
            transaction=transaction,
            upload_id=upload_id,
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
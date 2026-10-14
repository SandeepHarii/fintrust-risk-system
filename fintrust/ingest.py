
import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote_plus

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from fintrust.db import get_db_connection, insert_transaction
from fintrust.dynamo import put_risk_event
from fintrust.validators import validate_transaction


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialise AWS clients at module level for Lambda connection reuse.
_s3 = boto3.client("s3")
_sqs = boto3.client("sqs")
_cloudwatch = boto3.client("cloudwatch")

QUARANTINE_BUCKET = "fintrust-prod-quarantine-transactions"
PROCESSED_BUCKET = "fintrust-prod-processed-transactions"

TRANSACTION_QUEUE_URL = (
    "https://sqs.eu-north-1.amazonaws.com/051084216179/"
    "fintrust-prod-transaction-queue.fifo"
)

METRIC_NAMESPACE = "FinTrust/ETL"


def publish_metrics(
    processed_transactions: int,
    ingestion_errors: int,
    high_risk_transactions: int,
) -> None:
    """Publish aggregated ETL metrics to CloudWatch."""
    try:
        _cloudwatch.put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "ProcessedTransactions",
                    "Dimensions": [
                        {
                            "Name": "Environment",
                            "Value": "prod",
                        }
                    ],
                    "Value": processed_transactions,
                    "Unit": "Count",
                },
                {
                    "MetricName": "IngestionErrors",
                    "Dimensions": [
                        {
                            "Name": "Environment",
                            "Value": "prod",
                        }
                    ],
                    "Value": ingestion_errors,
                    "Unit": "Count",
                },
                {
                    "MetricName": "HighRiskTransactions",
                    "Dimensions": [
                        {
                            "Name": "Environment",
                            "Value": "prod",
                        }
                    ],
                    "Value": high_risk_transactions,
                    "Unit": "Count",
                },
            ],
        )

        logger.info(
            json.dumps(
                {
                    "event": "cloudwatch_metrics_published",
                    "namespace": METRIC_NAMESPACE,
                    "processed_transactions": processed_transactions,
                    "ingestion_errors": ingestion_errors,
                    "high_risk_transactions": high_risk_transactions,
                },
                default=str,
            )
        )
    except Exception as exc:
        logger.error(
            json.dumps(
                {
                    "event": "cloudwatch_metrics_failed",
                    "namespace": METRIC_NAMESPACE,
                    "error": str(exc),
                },
                default=str,
            )
        )


def calculate_risk_pre_score(
    transaction: dict[str, Any],
) -> tuple[str, list[str]]:
    """Calculate the initial risk level from transaction-level rules."""
    reasons: list[str] = []

    try:
        amount = float(transaction["amount"])
    except (KeyError, TypeError, ValueError):
        return "HIGH", ["INVALID_AMOUNT"]

    if amount > 50000:
        reasons.append("HIGH_AMOUNT")

    source_country = str(
        transaction["source_country"]
    ).strip().upper()

    destination_country = str(
        transaction["destination_country"]
    ).strip().upper()

    if source_country != destination_country:
        reasons.append("CROSS_BORDER")

    # HIGH_AMOUNT is a mandatory HIGH-risk condition.
    if "HIGH_AMOUNT" in reasons:
        return "HIGH", reasons

    # Cross-border-only transactions are MEDIUM risk.
    if "CROSS_BORDER" in reasons:
        return "MEDIUM", reasons

    return "LOW", []


def quarantine_row(
    row: dict[str, Any],
    row_number: int,
    errors: list[str],
    source_bucket: str,
    source_key: str,
) -> None:
    """Store an invalid transaction row in the quarantine S3 bucket."""
    transaction_id = row.get(
        "transaction_id",
        f"row-{row_number}",
    )

    quarantine_record = {
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        "source_bucket": source_bucket,
        "source_key": source_key,
        "row_number": row_number,
        "transaction": row,
        "validation_errors": errors,
    }

    quarantine_key = (
        f"{source_key}/row-{row_number}-{transaction_id}.json"
    )

    _s3.put_object(
        Bucket=QUARANTINE_BUCKET,
        Key=quarantine_key,
        Body=json.dumps(
            quarantine_record,
            default=str,
        ).encode("utf-8"),
        ContentType="application/json",
    )

    logger.warning(
        json.dumps(
            {
                "event": "transaction_quarantined",
                "row_number": row_number,
                "transaction_id": transaction_id,
                "quarantine_bucket": QUARANTINE_BUCKET,
                "quarantine_key": quarantine_key,
                "errors": errors,
            },
            default=str,
        )
    )


def send_transaction_to_queue(
    transaction: dict[str, Any],
    risk_level: str,
    risk_reasons: list[str],
) -> None:
    """Send a valid transaction to the FinTrust FIFO transaction queue."""
    account_id = str(transaction["account_id"])
    transaction_id = str(transaction["transaction_id"])

    message = {
        "transaction": transaction,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
    }

    response = _sqs.send_message(
        QueueUrl=TRANSACTION_QUEUE_URL,
        MessageBody=json.dumps(
            message,
            default=str,
        ),
        MessageGroupId=account_id,
        MessageDeduplicationId=transaction_id,
    )

    logger.info(
        json.dumps(
            {
                "event": "transaction_queued",
                "transaction_id": transaction_id,
                "account_id": account_id,
                "risk_level": risk_level,
                "risk_reasons": risk_reasons,
                "queue_url": TRANSACTION_QUEUE_URL,
                "message_id": response.get("MessageId"),
            },
            default=str,
        )
    )


def store_transaction_in_rds(
    transaction: dict[str, Any],
    risk_level: str,
) -> None:
    """Insert a validated transaction into PostgreSQL."""
    with get_db_connection() as conn:
        insert_transaction(
            conn=conn,
            transaction=transaction,
            risk_flag=risk_level,
        )

    logger.info(
        json.dumps(
            {
                "event": "transaction_stored_rds",
                "transaction_id": transaction.get("transaction_id"),
                "account_id": transaction.get("account_id"),
                "risk_level": risk_level,
            },
            default=str,
        )
    )


def store_risk_event_in_dynamodb(
    transaction: dict[str, Any],
    risk_level: str,
    risk_reasons: list[str],
) -> None:
    """Store the transaction risk event in DynamoDB."""
    account_id = str(transaction["account_id"])
    transaction_timestamp = str(transaction["tx_date"])
    transaction_id = str(transaction["transaction_id"])

    risk_event = {
        "transaction_id": transaction_id,
        "risk_level": risk_level,
        "risk_reason": (
            ",".join(risk_reasons) if risk_reasons else "NONE"
        ),
    }

    put_risk_event(
        account_id=account_id,
        transaction_timestamp=transaction_timestamp,
        risk_event=risk_event,
    )

    logger.info(
        json.dumps(
            {
                "event": "risk_event_stored_dynamodb",
                "transaction_id": transaction_id,
                "account_id": account_id,
                "transaction_timestamp": transaction_timestamp,
                "risk_level": risk_level,
                "risk_reasons": risk_reasons,
            },
            default=str,
        )
    )


def process_valid_transaction(
    transaction: dict[str, Any],
    risk_level: str,
    risk_reasons: list[str],
) -> None:
    """Persist and queue a validated transaction."""
    store_transaction_in_rds(
        transaction=transaction,
        risk_level=risk_level,
    )

    store_risk_event_in_dynamodb(
        transaction=transaction,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
    )

    send_transaction_to_queue(
        transaction=transaction,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
    )


def store_processed_parquet(
    transactions: list[dict[str, Any]],
    source_key: str,
) -> str | None:
    """Store successfully processed transactions as a Parquet object in S3."""
    if not transactions:
        logger.info(
            json.dumps(
                {
                    "event": "no_valid_transactions_to_export",
                    "source_key": source_key,
                }
            )
        )
        return None

    table = pa.Table.from_pylist(transactions)

    buffer = io.BytesIO()
    pq.write_table(
        table,
        buffer,
        compression="snappy",
    )
    buffer.seek(0)

    source_filename = source_key.rsplit("/", 1)[-1]
    source_stem = source_filename.rsplit(".", 1)[0]
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    processed_key = (
        f"processed/{source_stem}-{timestamp}.parquet"
    )

    _s3.put_object(
        Bucket=PROCESSED_BUCKET,
        Key=processed_key,
        Body=buffer.getvalue(),
        ContentType="application/vnd.apache.parquet",
    )

    logger.info(
        json.dumps(
            {
                "event": "processed_parquet_uploaded",
                "source_key": source_key,
                "processed_bucket": PROCESSED_BUCKET,
                "processed_key": processed_key,
                "transaction_count": len(transactions),
            }
        )
    )

    return processed_key


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Process a FinTrust transaction CSV uploaded to S3."""
    total_rows = 0
    valid_rows = 0
    invalid_rows = 0
    high_risk_rows = 0

    logger.info(
        json.dumps(
            {
                "event": "ingest_lambda_invoked",
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
        bucket = record["s3"]["bucket"]["name"]
        object_key = unquote_plus(
            record["s3"]["object"]["key"]
        )

        response = _s3.get_object(
            Bucket=bucket,
            Key=object_key,
        )

        csv_content = response["Body"].read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(csv_content))

        # Each source CSV gets its own processed Parquet object.
        processed_transactions: list[dict[str, Any]] = []
        file_total_rows = 0
        file_valid_rows = 0
        file_invalid_rows = 0

        for row_number, row in enumerate(reader, start=2):
            total_rows += 1
            file_total_rows += 1

            is_valid, errors = validate_transaction(row)

            if is_valid:
                risk_level, risk_reasons = calculate_risk_pre_score(
                    row
                )

                logger.info(
                    json.dumps(
                        {
                            "event": "transaction_pre_scored",
                            "row_number": row_number,
                            "transaction_id": row.get(
                                "transaction_id"
                            ),
                            "account_id": row.get("account_id"),
                            "risk_level": risk_level,
                            "risk_reasons": risk_reasons,
                        }
                    )
                )

                # Only collect the record after all existing persistence
                # and queue operations have succeeded.
                process_valid_transaction(
                    transaction=row,
                    risk_level=risk_level,
                    risk_reasons=risk_reasons,
                )

                processed_record = dict(row)
                processed_record["risk_level"] = risk_level
                processed_record["risk_reasons"] = risk_reasons
                processed_record["processed_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )

                processed_transactions.append(processed_record)

                valid_rows += 1
                file_valid_rows += 1

                if risk_level == "HIGH":
                    high_risk_rows += 1

            else:
                invalid_rows += 1
                file_invalid_rows += 1

                quarantine_row(
                    row=row,
                    row_number=row_number,
                    errors=errors,
                    source_bucket=bucket,
                    source_key=object_key,
                )

        processed_key = store_processed_parquet(
            transactions=processed_transactions,
            source_key=object_key,
        )

        logger.info(
            json.dumps(
                {
                    "event": "csv_processed",
                    "bucket": bucket,
                    "object_key": object_key,
                    "total_rows": file_total_rows,
                    "valid_rows": file_valid_rows,
                    "invalid_rows": file_invalid_rows,
                    "processed_bucket": (
                        PROCESSED_BUCKET if processed_key else None
                    ),
                    "processed_key": processed_key,
                }
            )
        )

    publish_metrics(
        processed_transactions=valid_rows,
        ingestion_errors=invalid_rows,
        high_risk_transactions=high_risk_rows,
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "CSV processed successfully",
                "total_rows": total_rows,
                "valid_rows": valid_rows,
                "invalid_rows": invalid_rows,
            }
        ),
    }
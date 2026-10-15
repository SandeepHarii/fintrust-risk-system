
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

from fintrust import dynamo
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
) -> None:
    """Publish aggregated ingestion metrics to CloudWatch."""
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
            ],
        )

        logger.info(
            json.dumps(
                {
                    "event": "cloudwatch_metrics_published",
                    "namespace": METRIC_NAMESPACE,
                    "processed_transactions": processed_transactions,
                    "ingestion_errors": ingestion_errors,
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
    upload_id: str | None = None,
) -> None:
    """Send a validated transaction to the FinTrust FIFO transaction queue."""
    account_id = str(transaction["account_id"])
    transaction_id = str(transaction["transaction_id"])

    # Risk scoring is performed downstream by the scoring Lambda.
    message = {
        "transaction": transaction,
    }

    if upload_id:
        message["upload_id"] = upload_id

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
                "upload_id": upload_id,
                "queue_url": TRANSACTION_QUEUE_URL,
                "message_id": response.get("MessageId"),
            },
            default=str,
        )
    )


def process_valid_transaction(
    transaction: dict[str, Any],
    upload_id: str | None = None,
) -> None:
    """Send a validated transaction to SQS FIFO for risk scoring."""
    send_transaction_to_queue(
        transaction=transaction,
        upload_id=upload_id,
    )


def store_processed_parquet(
    transactions: list[dict[str, Any]],
    source_key: str,
) -> str | None:
    """Store successfully queued transactions as Parquet in S3."""
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


def _get_s3_records(
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    """Support both S3 events and Step Functions upload input."""
    records = event.get("Records")

    if records:
        return records

    bucket = event.get("bucket")
    object_key = event.get("object_key")

    if bucket and object_key:
        return [
            {
                "s3": {
                    "bucket": {
                        "name": bucket,
                    },
                    "object": {
                        "key": object_key,
                    },
                }
            }
        ]

    raise ValueError(
        "The event must contain S3 Records or bucket and object_key."
    )


def _mark_upload_failed(
    upload_id: str | None,
    exc: Exception,
) -> None:
    """Record an upload failure without masking the original exception."""
    if not upload_id:
        return

    try:
        dynamo.mark_upload_failed(
            upload_id=upload_id,
            failure_reason=str(exc)[:1000],
        )

    except Exception:
        logger.exception(
            json.dumps(
                {
                    "event": "upload_failure_tracking_failed",
                    "upload_id": upload_id,
                }
            )
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Validate an uploaded CSV, quarantine invalid rows and queue valid rows."""
    upload_id = event.get("upload_id")

    total_rows = 0
    valid_rows = 0
    invalid_rows = 0
    queued_rows = 0

    logger.info(
        json.dumps(
            {
                "event": "ingest_lambda_invoked",
                "record_count": len(event.get("Records", [])),
                "upload_id": upload_id,
                "request_id": getattr(
                    context,
                    "aws_request_id",
                    None,
                ),
            }
        )
    )

    try:
        records = _get_s3_records(event)

        if upload_id:
            dynamo.mark_ingestion_started(upload_id)

        # First phase: read and validate all files.
        # No valid transactions are queued until validation is complete.
        file_work: list[dict[str, Any]] = []

        for record in records:
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

            valid_transactions: list[dict[str, Any]] = []

            file_total_rows = 0
            file_valid_rows = 0
            file_invalid_rows = 0

            for row_number, row in enumerate(reader, start=2):
                total_rows += 1
                file_total_rows += 1

                is_valid, errors = validate_transaction(row)

                if is_valid:
                    valid_transactions.append(dict(row))

                    valid_rows += 1
                    file_valid_rows += 1

                else:
                    quarantine_row(
                        row=row,
                        row_number=row_number,
                        errors=errors,
                        source_bucket=bucket,
                        source_key=object_key,
                    )

                    invalid_rows += 1
                    file_invalid_rows += 1

            file_work.append(
                {
                    "bucket": bucket,
                    "object_key": object_key,
                    "valid_transactions": valid_transactions,
                    "total_rows": file_total_rows,
                    "valid_rows": file_valid_rows,
                    "invalid_rows": file_invalid_rows,
                }
            )

        # Record validation counts before queueing starts.
        if upload_id:
            dynamo.set_upload_validation_results(
                upload_id=upload_id,
                total_records=total_rows,
                valid_records=valid_rows,
                quarantined_records=invalid_rows,
            )

        # Second phase: queue validated transactions.
        # Upload IDs allow scoring workers to update the correct upload.
        processed_files: list[dict[str, Any]] = []

        for file_data in file_work:
            queued_transactions: list[dict[str, Any]] = []

            for transaction in file_data["valid_transactions"]:
                if upload_id:
                    process_valid_transaction(
                        transaction=transaction,
                        upload_id=upload_id,
                    )
                else:
                    process_valid_transaction(
                        transaction=transaction,
                    )

                processed_record = dict(transaction)
                processed_record["queued_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )

                queued_transactions.append(processed_record)
                queued_rows += 1

            processed_key = store_processed_parquet(
                transactions=queued_transactions,
                source_key=file_data["object_key"],
            )

            file_result = {
                "bucket": file_data["bucket"],
                "object_key": file_data["object_key"],
                "total_rows": file_data["total_rows"],
                "valid_rows": file_data["valid_rows"],
                "invalid_rows": file_data["invalid_rows"],
                "processed_bucket": (
                    PROCESSED_BUCKET if processed_key else None
                ),
                "processed_key": processed_key,
            }

            processed_files.append(file_result)

            logger.info(
                json.dumps(
                    {
                        "event": "csv_processed",
                        **file_result,
                    }
                )
            )

        # Queueing is complete only after every valid transaction
        # has been successfully sent to SQS.
        if upload_id:
            dynamo.mark_upload_queued(
                upload_id=upload_id,
                queued_records=queued_rows,
            )

        publish_metrics(
            processed_transactions=queued_rows,
            ingestion_errors=invalid_rows,
        )

        result = {
            "message": "CSV ingestion completed successfully",
            "upload_id": upload_id,
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
            "queued_rows": queued_rows,
            "files": processed_files,
        }

        logger.info(
            json.dumps(
                {
                    "event": "ingestion_completed",
                    **result,
                },
                default=str,
            )
        )

        return {
            "statusCode": 200,
            "body": json.dumps(result, default=str),
        }

    except Exception as exc:
        logger.exception(
            json.dumps(
                {
                    "event": "ingestion_failed",
                    "upload_id": upload_id,
                    "error": str(exc),
                },
                default=str,
            )
        )

        _mark_upload_failed(
            upload_id=upload_id,
            exc=exc,
        )

        raise

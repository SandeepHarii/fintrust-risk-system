
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------
# DynamoDB configuration
# ---------------------------------------------------------------------

DYNAMODB_TABLE_NAME = os.getenv(
    "DYNAMODB_TABLE_NAME",
    "fintrust-prod-risk-events",
)

UPLOAD_TRACKING_TABLE_NAME = os.getenv(
    "UPLOAD_TRACKING_TABLE_NAME",
    "fintrust-prod-upload-tracking",
)

dynamodb = boto3.resource("dynamodb")

# Existing risk-events table.
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# Separate table for CSV upload progress.
upload_tracking_table = dynamodb.Table(
    UPLOAD_TRACKING_TABLE_NAME
)

# Use a separate low-level client for transactions.
# The DynamoDB resource client has automatic serialization handlers,
# which must not be combined with manually serialized AttributeValues.
_dynamodb_client = boto3.client(
    "dynamodb",
    region_name=dynamodb.meta.client.meta.region_name,
)

_serializer = TypeSerializer()


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------

UPLOAD_STAGES = {
    "csv_uploaded",
    "ingestion_started",
    "validation",
    "transactions_queued",
    "risk_scoring",
    "results_persisted",
}

VALID_STAGE_STATUSES = {
    "WAITING",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
}


def _utc_now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _serialize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Serialize a Python dictionary for low-level DynamoDB operations."""
    return {
        key: _serializer.serialize(value)
        for key, value in item.items()
    }


def _get_upload_summary(
    upload_id: str,
) -> dict[str, Any] | None:
    """Retrieve an upload's summary using a strongly consistent read."""
    response = upload_tracking_table.get_item(
        Key={
            "upload_id": upload_id,
            "record_type": "SUMMARY",
        },
        ConsistentRead=True,
    )

    return response.get("Item")


# ---------------------------------------------------------------------
# Existing risk-event functionality
# ---------------------------------------------------------------------

def put_risk_event(
    account_id: str,
    transaction_id: str,
    transaction_timestamp: str,
    risk_event: dict[str, Any],
) -> None:
    """Store a risk event in DynamoDB."""
    item = {
        **risk_event,
        "account_id": account_id,
        "transaction_id": transaction_id,
        "transaction_timestamp": transaction_timestamp,
    }

    table.put_item(Item=item)


def get_risk_event(
    account_id: str,
    transaction_id: str,
) -> dict[str, Any] | None:
    """Retrieve a single risk event using its account and transaction ID."""
    response = table.get_item(
        Key={
            "account_id": account_id,
            "transaction_id": transaction_id,
        }
    )

    return response.get("Item")


def get_account_risk_events(
    account_id: str,
) -> list[dict[str, Any]]:
    """Retrieve all risk events for an account."""
    items = []

    response = table.query(
        KeyConditionExpression=Key("account_id").eq(account_id)
    )

    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("account_id").eq(account_id),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )

        items.extend(response.get("Items", []))

    return items


# ---------------------------------------------------------------------
# Upload tracking
# ---------------------------------------------------------------------

def create_upload_tracking(
    upload_id: str,
    bucket: str,
    object_key: str,
) -> None:
    """
    Create the initial tracking record for a CSV upload.

    The CSV has already been uploaded successfully to S3 when this
    function is called.
    """
    now = _utc_now()

    item = {
        "upload_id": upload_id,
        "record_type": "SUMMARY",
        "bucket": bucket,
        "object_key": object_key,
        "status": "PROCESSING",
        "current_stage": "csv_uploaded",
        "stages": {
            "csv_uploaded": "COMPLETED",
            "ingestion_started": "WAITING",
            "validation": "WAITING",
            "transactions_queued": "WAITING",
            "risk_scoring": "WAITING",
            "results_persisted": "WAITING",
        },
        "total_records": 0,
        "valid_records": 0,
        "quarantined_records": 0,
        "queued_records": 0,
        "completed_records": 0,
        "created_at": now,
        "updated_at": now,
    }

    upload_tracking_table.put_item(
        Item=item,
        ConditionExpression=(
            "attribute_not_exists(upload_id) "
            "AND attribute_not_exists(record_type)"
        ),
    )


def set_upload_execution_arn(
    upload_id: str,
    execution_arn: str,
) -> None:
    """Associate a Step Functions execution with an upload."""
    upload_tracking_table.update_item(
        Key={
            "upload_id": upload_id,
            "record_type": "SUMMARY",
        },
        UpdateExpression=(
            "SET execution_arn = :execution_arn, "
            "updated_at = :updated_at"
        ),
        ConditionExpression="attribute_exists(upload_id)",
        ExpressionAttributeValues={
            ":execution_arn": execution_arn,
            ":updated_at": _utc_now(),
        },
    )


def set_upload_stage(
    upload_id: str,
    stage: str,
    status: str,
) -> None:
    """
    Update an individual upload stage.

    Stage keys and statuses are restricted to known values so callers
    cannot accidentally create inconsistent tracking fields.
    """
    if stage not in UPLOAD_STAGES:
        raise ValueError(f"Unsupported upload stage: {stage}")

    if status not in VALID_STAGE_STATUSES:
        raise ValueError(f"Unsupported stage status: {status}")

    upload_tracking_table.update_item(
        Key={
            "upload_id": upload_id,
            "record_type": "SUMMARY",
        },
        UpdateExpression=(
            "SET #stages.#stage = :status, "
            "#current_stage = :current_stage, "
            "#updated_at = :updated_at"
        ),
        ConditionExpression="attribute_exists(upload_id)",
        ExpressionAttributeNames={
            "#stages": "stages",
            "#stage": stage,
            "#current_stage": "current_stage",
            "#updated_at": "updated_at",
        },
        ExpressionAttributeValues={
            ":status": status,
            ":current_stage": stage,
            ":updated_at": _utc_now(),
        },
    )


def mark_ingestion_started(
    upload_id: str,
) -> None:
    """Record that the ingestion Lambda has started processing the upload."""
    set_upload_stage(
        upload_id=upload_id,
        stage="ingestion_started",
        status="COMPLETED",
    )

    set_upload_stage(
        upload_id=upload_id,
        stage="validation",
        status="IN_PROGRESS",
    )


def set_upload_validation_results(
    upload_id: str,
    total_records: int,
    valid_records: int,
    quarantined_records: int,
) -> None:
    """
    Store the final CSV validation counts.

    Queueing remains IN_PROGRESS until ingestion explicitly confirms
    that all valid records have been sent to SQS.
    """
    if min(total_records, valid_records, quarantined_records) < 0:
        raise ValueError("Upload record counts cannot be negative.")

    if valid_records + quarantined_records != total_records:
        raise ValueError(
            "Valid and quarantined record counts must equal total records."
        )

    upload_tracking_table.update_item(
        Key={
            "upload_id": upload_id,
            "record_type": "SUMMARY",
        },
        UpdateExpression=(
            "SET total_records = :total, "
            "valid_records = :valid, "
            "quarantined_records = :quarantined, "
            "#stages.#ingestion_started = :completed, "
            "#stages.#validation = :completed, "
            "#stages.#transactions_queued = :in_progress, "
            "#current_stage = :current_stage, "
            "updated_at = :updated_at"
        ),
        ConditionExpression="attribute_exists(upload_id)",
        ExpressionAttributeNames={
            "#stages": "stages",
            "#ingestion_started": "ingestion_started",
            "#validation": "validation",
            "#transactions_queued": "transactions_queued",
            "#current_stage": "current_stage",
        },
        ExpressionAttributeValues={
            ":total": total_records,
            ":valid": valid_records,
            ":quarantined": quarantined_records,
            ":completed": "COMPLETED",
            ":in_progress": "IN_PROGRESS",
            ":current_stage": "transactions_queued",
            ":updated_at": _utc_now(),
        },
    )


def _complete_upload_if_ready(
    upload_id: str,
) -> None:
    """
    Complete scoring and persistence stages once all valid records
    have been persisted and queueing has finished.
    """
    summary = _get_upload_summary(upload_id)

    if summary is None:
        raise ValueError(
            f"Upload tracking record not found: {upload_id}"
        )

    valid_records = int(summary.get("valid_records", 0))
    completed_records = int(summary.get("completed_records", 0))

    stages = summary.get("stages", {})

    queueing_completed = (
        stages.get("transactions_queued") == "COMPLETED"
    )

    if not queueing_completed:
        return

    if completed_records < valid_records:
        return

    # Do not turn an explicitly failed upload into a completed upload.
    if summary.get("status") == "FAILED":
        return

    try:
        upload_tracking_table.update_item(
            Key={
                "upload_id": upload_id,
                "record_type": "SUMMARY",
            },
            UpdateExpression=(
                "SET #stages.#risk_scoring = :completed, "
                "#stages.#results_persisted = :completed, "
                "#current_stage = :current_stage, "
                "#status = :status, "
                "#updated_at = :updated_at"
            ),
            ConditionExpression=(
                "#stages.#transactions_queued = :completed "
                "AND #completed_records >= #valid_records "
                "AND #status <> :failed"
            ),
            ExpressionAttributeNames={
                "#stages": "stages",
                "#risk_scoring": "risk_scoring",
                "#results_persisted": "results_persisted",
                "#transactions_queued": "transactions_queued",
                "#completed_records": "completed_records",
                "#valid_records": "valid_records",
                "#current_stage": "current_stage",
                "#status": "status",
                "#updated_at": "updated_at",
            },
            ExpressionAttributeValues={
                ":completed": "COMPLETED",
                ":current_stage": "results_persisted",
                ":status": "COMPLETED",
                ":failed": "FAILED",
                ":updated_at": _utc_now(),
            },
        )

    except ClientError as exc:
        error_code = exc.response.get(
            "Error", {}
        ).get("Code")

        if error_code != "ConditionalCheckFailedException":
            raise

        # A failure may have been recorded concurrently. Recheck the
        # summary to distinguish that case from an unexpected condition.
        latest_summary = _get_upload_summary(upload_id)

        if latest_summary and latest_summary.get("status") == "FAILED":
            return

        raise


def mark_upload_queued(
    upload_id: str,
    queued_records: int,
) -> None:
    """
    Mark queueing as complete after every valid transaction has been
    successfully sent to SQS.
    """
    if queued_records < 0:
        raise ValueError("Queued record count cannot be negative.")

    upload_tracking_table.update_item(
        Key={
            "upload_id": upload_id,
            "record_type": "SUMMARY",
        },
        UpdateExpression=(
            "SET queued_records = :queued, "
            "#stages.#transactions_queued = :completed, "
            "#current_stage = :current_stage, "
            "#updated_at = :updated_at"
        ),
        ConditionExpression=(
            "attribute_exists(upload_id) "
            "AND #valid_records = :queued"
        ),
        ExpressionAttributeNames={
            "#stages": "stages",
            "#transactions_queued": "transactions_queued",
            "#current_stage": "current_stage",
            "#updated_at": "updated_at",
            "#valid_records": "valid_records",
        },
        ExpressionAttributeValues={
            ":queued": queued_records,
            ":completed": "COMPLETED",
            ":current_stage": (
                "risk_scoring"
                if queued_records > 0
                else "results_persisted"
            ),
            ":updated_at": _utc_now(),
        },
    )

    if queued_records > 0:
        # A scoring worker may already have completed all transactions
        # between the queue-stage update and this update. Never regress
        # a completed scoring stage back to IN_PROGRESS.
        try:
            upload_tracking_table.update_item(
                Key={
                    "upload_id": upload_id,
                    "record_type": "SUMMARY",
                },
                UpdateExpression=(
                    "SET #stages.#risk_scoring = :in_progress, "
                    "#current_stage = :current_stage, "
                    "#updated_at = :updated_at"
                ),
                ConditionExpression=(
                    "#stages.#transactions_queued = :completed "
                    "AND #stages.#risk_scoring <> :completed"
                ),
                ExpressionAttributeNames={
                    "#stages": "stages",
                    "#risk_scoring": "risk_scoring",
                    "#transactions_queued": "transactions_queued",
                    "#current_stage": "current_stage",
                    "#updated_at": "updated_at",
                },
                ExpressionAttributeValues={
                    ":in_progress": "IN_PROGRESS",
                    ":completed": "COMPLETED",
                    ":current_stage": "risk_scoring",
                    ":updated_at": _utc_now(),
                },
            )

        except ClientError as exc:
            error_code = exc.response.get(
                "Error", {}
            ).get("Code")

            if error_code != "ConditionalCheckFailedException":
                raise

    _complete_upload_if_ready(upload_id)


def mark_transaction_persisted(
    upload_id: str,
    transaction_id: str,
) -> bool:
    """
    Record successful persistence of a transaction in PostgreSQL
    and DynamoDB.

    A conditional marker put and summary counter increment happen
    atomically. Duplicate SQS deliveries therefore cannot increment
    completed_records more than once.

    Returns True when a new completion marker was created.
    Returns False when the transaction was already recorded.
    """
    if not upload_id:
        raise ValueError("upload_id is required.")

    if not transaction_id:
        raise ValueError("transaction_id is required.")

    now = _utc_now()

    marker = {
        "upload_id": upload_id,
        "record_type": f"TX#{transaction_id}",
        "transaction_id": transaction_id,
        "persisted_at": now,
    }

    try:
        _dynamodb_client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": UPLOAD_TRACKING_TABLE_NAME,
                        "Item": _serialize_item(marker),
                        "ConditionExpression": (
                            "attribute_not_exists(upload_id) "
                            "AND attribute_not_exists(record_type)"
                        ),
                    }
                },
                {
                    "Update": {
                        "TableName": UPLOAD_TRACKING_TABLE_NAME,
                        "Key": _serialize_item(
                            {
                                "upload_id": upload_id,
                                "record_type": "SUMMARY",
                            }
                        ),
                        "UpdateExpression": (
                            "SET updated_at = :updated_at "
                            "ADD completed_records :one"
                        ),
                        "ConditionExpression": (
                            "attribute_exists(upload_id) "
                            "AND record_type = :summary"
                        ),
                        "ExpressionAttributeValues": _serialize_item(
                            {
                                ":updated_at": now,
                                ":one": 1,
                                ":summary": "SUMMARY",
                            }
                        ),
                    }
                },
            ]
        )

    except ClientError as exc:
        error_code = exc.response.get(
            "Error", {}
        ).get("Code")

        if error_code in {
            "TransactionCanceledException",
            "ConditionalCheckFailedException",
        }:
            existing_marker = upload_tracking_table.get_item(
                Key={
                    "upload_id": upload_id,
                    "record_type": f"TX#{transaction_id}",
                },
                ConsistentRead=True,
            ).get("Item")

            if existing_marker:
                # Retry completion checks too. The original transaction
                # may have committed its marker before a later completion
                # update failed.
                _complete_upload_if_ready(upload_id)
                return False

        raise

    _complete_upload_if_ready(upload_id)

    return True


def mark_upload_failed(
    upload_id: str,
    failure_reason: str,
) -> None:
    """Mark an upload as failed while preserving its existing stage history."""
    upload_tracking_table.update_item(
        Key={
            "upload_id": upload_id,
            "record_type": "SUMMARY",
        },
        UpdateExpression=(
            "SET #status = :failed, "
            "failure_reason = :reason, "
            "#updated_at = :updated_at"
        ),
        ConditionExpression="attribute_exists(upload_id)",
        ExpressionAttributeNames={
            "#status": "status",
            "#updated_at": "updated_at",
        },
        ExpressionAttributeValues={
            ":failed": "FAILED",
            ":reason": failure_reason,
            ":updated_at": _utc_now(),
        },
    )


def get_upload_tracking(
    upload_id: str,
) -> dict[str, Any] | None:
    """Retrieve the current progress summary for a CSV upload."""
    return _get_upload_summary(upload_id)
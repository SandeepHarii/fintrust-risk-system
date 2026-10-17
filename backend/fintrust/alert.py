
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ses = boto3.client("ses", region_name="eu-north-1")
_dynamodb = boto3.client("dynamodb", region_name="eu-north-1")

TABLE_NAME = "fintrust-prod-upload-tracking"

SENDER_EMAIL = os.getenv(
    "SES_SENDER_EMAIL",
    "Sandeep.Hari09@gmail.com",
)

COMPLIANCE_EMAIL = os.getenv(
    "SES_COMPLIANCE_EMAIL",
    "sandeep.hari19@gmail.com",
)


def _send_email(subject: str, body: str) -> str:
    response = _ses.send_email(
        Source=SENDER_EMAIL,
        Destination={"ToAddresses": [COMPLIANCE_EMAIL]},
        Message={
            "Subject": {
                "Data": subject,
                "Charset": "UTF-8",
            },
            "Body": {
                "Text": {
                    "Data": body,
                    "Charset": "UTF-8",
                }
            },
        },
    )

    return response.get("MessageId")


def _number(item: dict, field: str) -> int:
    return int(item.get(field, {}).get("N", "0"))


def _string(item: dict, *fields: str) -> str:
    for field in fields:
        value = item.get(field, {}).get("S")
        if value:
            return value

    return "The upload could not be completed successfully."


def _send_upload_notification(
    upload_id: str,
    notification_type: str,
    expected_status: str,
) -> dict[str, Any]:

    response = _dynamodb.get_item(
        TableName=TABLE_NAME,
        Key={
            "upload_id": {"S": upload_id},
            "record_type": {"S": "SUMMARY"},
        },
        ConsistentRead=True,
    )

    summary = response.get("Item")

    if not summary:
        raise ValueError(f"Upload summary not found: {upload_id}")

    status = summary.get("status", {}).get("S")

    if status != expected_status:
        raise ValueError(
            f"Upload status is {status}, expected {expected_status}."
        )

    total = _number(summary, "total_records")
    valid = _number(summary, "valid_records")
    completed = _number(summary, "completed_records")
    duplicates = _number(summary, "duplicate_records")
    quarantined = _number(summary, "quarantined_records")

    if notification_type == "UPLOAD_COMPLETED" and completed != valid:
        raise ValueError(
            f"Upload is not fully processed: "
            f"{completed}/{valid} records completed."
        )

    new_records = max(completed - duplicates, 0)
    failed_records = max(valid - completed, 0)

    is_completed = notification_type == "UPLOAD_COMPLETED"

    record_type = (
        "COMPLETION_EMAIL" if is_completed else "FAILURE_EMAIL"
    )

    try:
        _dynamodb.put_item(
            TableName=TABLE_NAME,
            Item={
                "upload_id": {"S": upload_id},
                "record_type": {"S": record_type},
                "notification_status": {"S": "CLAIMED"},
                "created_at": {
                    "S": datetime.now(timezone.utc).isoformat()
                },
            },
            ConditionExpression=(
                "attribute_not_exists(upload_id) "
                "AND attribute_not_exists(record_type)"
            ),
        )

    except ClientError as exc:
        if (
            exc.response.get("Error", {}).get("Code")
            == "ConditionalCheckFailedException"
        ):
            logger.info(
                "%s notification already claimed for %s",
                notification_type,
                upload_id,
            )

            return {
                "status": "ALREADY_SENT_OR_CLAIMED",
                "upload_id": upload_id,
            }

        raise

    if is_completed:
        subject = f"FinTrust Upload Completed - {upload_id}"

        body = (
            "Hello,\n\n"
            "The transaction upload has been successfully completed.\n\n"
            "UPLOAD SUMMARY\n"
            "------------------------------\n"
            f"Upload ID: {upload_id}\n"
            f"Total transactions: {total}\n"
            f"New transactions processed: {new_records}\n"
            f"Duplicate transactions detected: {duplicates}\n"
            f"Failed transactions: {failed_records}\n"
            f"Quarantined transactions: {quarantined}\n"
            "Processing status: COMPLETED\n"
            "Completion: 100%\n\n"
            "All valid transactions have reached their final "
            "processing outcome.\n\n"
            "Regards,\n"
            "FinTrust Transaction Insights and Risk Monitoring System"
        )

    else:
        failure_reason = _string(
            summary,
            "failure_reason",
            "error_message",
            "failure_cause",
        )

        subject = f"FinTrust Upload Failed - {upload_id}"

        body = (
            "Hello,\n\n"
            "Your transaction upload could not be completed "
            "successfully. The processing workflow has reported "
            "a failure.\n\n"
            "UPLOAD SUMMARY\n"
            "------------------------------\n"
            f"Upload ID: {upload_id}\n"
            f"Total transactions: {total}\n"
            f"Valid transactions: {valid}\n"
            f"Transactions processed: {completed}\n"
            f"New transactions processed: {new_records}\n"
            f"Duplicate transactions detected: {duplicates}\n"
            f"Transactions not completed: {failed_records}\n"
            f"Quarantined transactions: {quarantined}\n"
            "Processing status: FAILED\n\n"
            f"Failure reason: {failure_reason}\n\n"
            "Please review the upload and resolve the issue before "
            "attempting to upload the affected transactions again.\n\n"
            "Regards,\n"
            "FinTrust Transaction Insights and Risk Monitoring System"
        )

    try:
        message_id = _send_email(subject, body)

    except Exception:
        _dynamodb.delete_item(
            TableName=TABLE_NAME,
            Key={
                "upload_id": {"S": upload_id},
                "record_type": {"S": record_type},
            },
        )
        raise

    logger.info(
        json.dumps({
            "event": "upload_notification_sent",
            "notification_type": notification_type,
            "upload_id": upload_id,
            "message_id": message_id,
        })
    )

    return {
        "status": "SENT",
        "upload_id": upload_id,
        "notification_type": notification_type,
        "message_id": message_id,
    }


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:

    notification_type = event.get("notification_type")

    if notification_type == "UPLOAD_COMPLETED":
        upload_id = event.get("upload_id")

        if not upload_id:
            raise ValueError(
                "upload_id is required for completion emails."
            )

        return _send_upload_notification(
            upload_id,
            "UPLOAD_COMPLETED",
            "COMPLETED",
        )

    if notification_type == "UPLOAD_FAILED":
        upload_id = event.get("upload_id")

        if not upload_id:
            raise ValueError(
                "upload_id is required for failure emails."
            )

        return _send_upload_notification(
            upload_id,
            "UPLOAD_FAILED",
            "FAILED",
        )

    # Existing high-risk compliance notification.
    alert_id = event.get("alert_id")
    transaction_id = event.get("transaction_id")
    account_id = event.get("account_id")
    risk_event_id = event.get("risk_event_id")
    reason = event.get("reason")
    risk_level = event.get("risk_level", "HIGH")

    if not alert_id or not transaction_id or not account_id:
        raise ValueError(
            "alert_id, transaction_id and account_id are required."
        )

    subject = (
        f"FinTrust High-Risk Transaction Alert - {transaction_id}"
    )

    body = (
        "A high-risk transaction requires compliance review.\n\n"
        f"Alert ID: {alert_id}\n"
        f"Transaction ID: {transaction_id}\n"
        f"Account ID: {account_id}\n"
        f"Risk Event ID: {risk_event_id}\n"
        f"Risk Level: {risk_level}\n"
        f"Reason: {reason}\n"
    )

    try:
        message_id = _send_email(subject, body)

        logger.info(
            json.dumps({
                "event": "alert_email_sent",
                "alert_id": alert_id,
                "transaction_id": transaction_id,
                "message_id": message_id,
            })
        )

        return {
            "statusCode": 200,
            "alert_id": alert_id,
            "message_id": message_id,
            "status": "SENT",
        }

    except Exception as exc:
        logger.error(
            json.dumps({
                "event": "alert_email_failed",
                "alert_id": alert_id,
                "transaction_id": transaction_id,
                "error": str(exc),
            })
        )
        raise
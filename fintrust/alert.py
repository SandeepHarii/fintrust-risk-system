import json
import logging
import os
from typing import Any

import boto3


logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ses = boto3.client("ses", region_name="eu-north-1")

SENDER_EMAIL = os.getenv(
    "SES_SENDER_EMAIL",
    "Sandeep.Hari09@gmail.com",
)

COMPLIANCE_EMAIL = os.getenv(
    "SES_COMPLIANCE_EMAIL",
    "sandeep.hari19@gmail.com",
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Send a high-risk transaction alert to the compliance recipient."""

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

    subject = f"FinTrust High-Risk Transaction Alert - {transaction_id}"

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
        response = _ses.send_email(
            Source=SENDER_EMAIL,
            Destination={
                "ToAddresses": [
                    COMPLIANCE_EMAIL,
                ]
            },
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

        logger.info(
            json.dumps(
                {
                    "event": "alert_email_sent",
                    "alert_id": alert_id,
                    "transaction_id": transaction_id,
                    "message_id": response.get("MessageId"),
                },
                default=str,
            )
        )

        return {
            "statusCode": 200,
            "alert_id": alert_id,
            "message_id": response.get("MessageId"),
            "status": "SENT",
        }

    except Exception as exc:
        logger.error(
            json.dumps(
                {
                    "event": "alert_email_failed",
                    "alert_id": alert_id,
                    "transaction_id": transaction_id,
                    "error": str(exc),
                },
                default=str,
            )
        )
        raise
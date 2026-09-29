import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key


DYNAMODB_TABLE_NAME = os.getenv(
    "DYNAMODB_TABLE_NAME",
    "fintrust-prod-risk-events",
)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE_NAME)


def put_risk_event(
    account_id: str,
    transaction_timestamp: str,
    risk_event: dict[str, Any],
) -> None:
    """Store a risk event in DynamoDB."""
    item = {
        "account_id": account_id,
        "transaction_timestamp": transaction_timestamp,
        **risk_event,
    }

    table.put_item(Item=item)


def get_risk_event(
    account_id: str,
    transaction_timestamp: str,
) -> dict[str, Any] | None:
    """Retrieve a single risk event."""
    response = table.get_item(
        Key={
            "account_id": account_id,
            "transaction_timestamp": transaction_timestamp,
        }
    )

    return response.get("Item")


def get_account_risk_events(
    account_id: str,
) -> list[dict[str, Any]]:
    """Retrieve all risk events for an account."""
    response = table.query(
        KeyConditionExpression=Key("account_id").eq(account_id)
    )

    return response.get("Items", [])
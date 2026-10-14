
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
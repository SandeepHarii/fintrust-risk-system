import boto3
from moto import mock_aws

from fintrust import dynamo


@mock_aws
def test_put_and_get_risk_event():
    dynamodb = boto3.resource("dynamodb", region_name="eu-north-1")

    dynamodb.create_table(
        TableName="fintrust-prod-risk-events",
        KeySchema=[
            {"AttributeName": "account_id", "KeyType": "HASH"},
            {"AttributeName": "transaction_timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "account_id", "AttributeType": "S"},
            {"AttributeName": "transaction_timestamp", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    account_id = "ACC-001"
    timestamp = "2026-09-29T10:00:00Z"

    dynamo.put_risk_event(
        account_id=account_id,
        transaction_timestamp=timestamp,
        risk_event={
            "risk_level": "HIGH",
            "reason": "HIGH_AMOUNT",
        },
    )

    result = dynamo.get_risk_event(
        account_id=account_id,
        transaction_timestamp=timestamp,
    )

    assert result is not None
    assert result["account_id"] == account_id
    assert result["transaction_timestamp"] == timestamp
    assert result["risk_level"] == "HIGH"
    assert result["reason"] == "HIGH_AMOUNT"


@mock_aws
def test_get_account_risk_events():
    dynamodb = boto3.resource("dynamodb", region_name="eu-north-1")

    dynamodb.create_table(
        TableName="fintrust-prod-risk-events",
        KeySchema=[
            {"AttributeName": "account_id", "KeyType": "HASH"},
            {"AttributeName": "transaction_timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "account_id", "AttributeType": "S"},
            {"AttributeName": "transaction_timestamp", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    dynamo.put_risk_event(
        account_id="ACC-001",
        transaction_timestamp="2026-09-29T10:00:00Z",
        risk_event={
            "risk_level": "HIGH",
            "reason": "HIGH_AMOUNT",
        },
    )

    dynamo.put_risk_event(
        account_id="ACC-001",
        transaction_timestamp="2026-09-29T11:00:00Z",
        risk_event={
            "risk_level": "MEDIUM",
            "reason": "CROSS_BORDER",
        },
    )

    results = dynamo.get_account_risk_events("ACC-001")

    assert len(results) == 2
    assert {item["risk_level"] for item in results} == {"HIGH", "MEDIUM"}
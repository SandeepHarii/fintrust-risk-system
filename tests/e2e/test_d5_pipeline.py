import csv
import io
import os
import time
import uuid

import boto3
import requests


API_BASE_URL = os.getenv(
    "FINTRUST_API_BASE_URL",
    "https://a1tia7lthb.execute-api.eu-north-1.amazonaws.com/prod",
)

API_KEY = os.getenv("FINTRUST_API_KEY")

AWS_REGION = "eu-north-1"

DYNAMODB_TABLE = "fintrust-prod-risk-events"

ALERT_LOG_GROUP = "/aws/lambda/fintrust-prod-alert"

ACCOUNT_ID = "909f8261-243d-4cb4-aa1b-3fad16d27521"


def create_test_csv(transaction_id: str) -> str:
    rows = [
        [
            transaction_id,
            ACCOUNT_ID,
            "2026-10-08T11:15:00+02:00",
            "60000.00",
            "ZAR",
            "PURCHASE",
            "ZA",
            "GB",
        ]
    ]

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "transaction_id",
            "account_id",
            "tx_date",
            "amount",
            "currency",
            "transaction_type",
            "source_country",
            "destination_country",
        ]
    )

    writer.writerows(rows)

    return output.getvalue()


def wait_for_transaction(transaction_id: str, timeout: int = 120) -> bool:
    end_time = time.time() + timeout

    while time.time() < end_time:
        response = requests.get(
            f"{API_BASE_URL}/transactions",
            headers={"x-api-key": API_KEY},
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        transactions = (
            data.get("transactions", [])
            if isinstance(data, dict)
            else data
        )

        if any(
            str(transaction.get("transaction_id")) == transaction_id
            for transaction in transactions
        ):
            return True

        time.sleep(5)

    return False


def wait_for_risk_event(transaction_id: str, timeout: int = 120) -> bool:
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=AWS_REGION,
    )

    table = dynamodb.Table(DYNAMODB_TABLE)

    end_time = time.time() + timeout

    while time.time() < end_time:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key(
                "account_id"
            ).eq(ACCOUNT_ID)
        )

        for item in response.get("Items", []):
            if str(item.get("transaction_id")) == transaction_id:
                return True

        time.sleep(5)

    return False


def wait_for_alert_log(transaction_id: str, timeout: int = 120) -> bool:
    logs = boto3.client(
        "logs",
        region_name=AWS_REGION,
    )

    end_time = time.time() + timeout

    while time.time() < end_time:
        response = logs.filter_log_events(
            logGroupName=ALERT_LOG_GROUP,
            filterPattern=f'"{transaction_id}"',
            startTime=int((time.time() - 10 * 60) * 1000),
        )

        if response.get("events"):
            return True

        time.sleep(5)

    return False


def test_d5_full_ingestion_to_alert_pipeline():
    assert API_KEY, (
        "FINTRUST_API_KEY environment variable is required. "
        "Use the existing FinTrust API key."
    )

    transaction_id = str(uuid.uuid4())

    csv_body = create_test_csv(transaction_id)

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "text/csv",
    }

    # 1. Upload transaction through the real API Gateway endpoint.
    response = requests.post(
        f"{API_BASE_URL}/upload",
        headers=headers,
        data=csv_body,
        timeout=30,
    )

    assert response.status_code == 202, response.text

    upload_result = response.json()

    assert upload_result["message"] == (
        "CSV upload accepted for asynchronous processing."
    )

    print(f"Uploaded transaction: {transaction_id}")
    print(f"S3 object: {upload_result.get('object_key')}")

    # 2. Verify asynchronous ingestion persisted the transaction.
    assert wait_for_transaction(transaction_id), (
        f"Transaction {transaction_id} was not persisted within the timeout."
    )

    print("PASS: API Gateway -> S3 -> Ingest -> RDS")

    # 3. Verify risk scoring produced a DynamoDB risk event.
    assert wait_for_risk_event(transaction_id), (
        f"Risk event for {transaction_id} was not found in DynamoDB."
    )

    print("PASS: Score -> DynamoDB risk event")

    # 4. Verify Alert Lambda processed the high-risk transaction.
    assert wait_for_alert_log(transaction_id), (
        f"Alert Lambda log entry for {transaction_id} was not found."
    )

    print("PASS: Alert Lambda invocation")

    print()
    print("D5 E2E PIPELINE PASSED")
    print("API Gateway -> S3 -> Ingest -> RDS -> SQS -> Score")
    print("-> DynamoDB -> Alert Lambda -> SES")
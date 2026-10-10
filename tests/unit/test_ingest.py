import io
import json

import pyarrow.parquet as pq

from fintrust import ingest
from fintrust.ingest import calculate_risk_pre_score


def base_transaction():
    return {
        "amount": "1000",
        "source_country": "ZA",
        "destination_country": "ZA",
    }


def test_low_risk_transaction():
    risk_level, reasons = calculate_risk_pre_score(base_transaction())

    assert risk_level == "LOW"
    assert reasons == []


def test_high_amount_transaction():
    transaction = base_transaction()
    transaction["amount"] = "50001"

    risk_level, reasons = calculate_risk_pre_score(transaction)

    assert risk_level == "HIGH"
    assert "HIGH_AMOUNT" in reasons


def test_cross_border_transaction():
    transaction = base_transaction()
    transaction["destination_country"] = "GB"

    risk_level, reasons = calculate_risk_pre_score(transaction)

    assert risk_level == "HIGH"
    assert "CROSS_BORDER" in reasons


def test_high_amount_and_cross_border_transaction():
    transaction = base_transaction()
    transaction["amount"] = "75000"
    transaction["destination_country"] = "GB"

    risk_level, reasons = calculate_risk_pre_score(transaction)

    assert risk_level == "HIGH"
    assert "HIGH_AMOUNT" in reasons
    assert "CROSS_BORDER" in reasons


def test_invalid_amount_is_high_risk():
    transaction = base_transaction()
    transaction["amount"] = "not-a-number"

    risk_level, reasons = calculate_risk_pre_score(transaction)

    assert risk_level == "HIGH"
    assert reasons == ["INVALID_AMOUNT"]


def test_country_comparison_is_case_insensitive():
    transaction = base_transaction()
    transaction["source_country"] = "za"
    transaction["destination_country"] = "ZA"

    risk_level, reasons = calculate_risk_pre_score(transaction)

    assert risk_level == "LOW"
    assert reasons == []


def test_publish_metrics(aws_resources):
    ingest.publish_metrics(
        processed_transactions=10,
        ingestion_errors=2,
        high_risk_transactions=3,
    )

    response = ingest._cloudwatch.list_metrics(
        Namespace="FinTrust/ETL"
    )

    metric_names = {
        metric["MetricName"]
        for metric in response["Metrics"]
    }

    assert "ProcessedTransactions" in metric_names
    assert "IngestionErrors" in metric_names
    assert "HighRiskTransactions" in metric_names


def test_send_transaction_to_queue(aws_resources):
    transaction = {
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "amount": "60000",
        "source_country": "ZA",
        "destination_country": "GB",
    }

    ingest.send_transaction_to_queue(
        transaction=transaction,
        risk_level="HIGH",
        risk_reasons=["HIGH_AMOUNT", "CROSS_BORDER"],
    )

    response = aws_resources["sqs"].receive_message(
        QueueUrl=aws_resources["queue_url"],
    )

    assert "Messages" in response
    assert len(response["Messages"]) == 1


def test_store_processed_parquet_round_trip(monkeypatch):
    transaction = {
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "amount": "60000",
        "currency": "ZAR",
        "risk_level": "HIGH",
        "risk_reasons": ["HIGH_AMOUNT"],
        "processed_at": "2026-10-10T12:00:00+00:00",
    }

    uploaded_objects = []

    def fake_put_object(**kwargs):
        uploaded_objects.append(kwargs)
        return {}

    monkeypatch.setattr(ingest._s3, "put_object", fake_put_object)

    processed_key = ingest.store_processed_parquet(
        transactions=[transaction],
        source_key="uploads/test-transactions.csv",
    )

    assert processed_key is not None
    assert processed_key.startswith("processed/test-transactions-")
    assert processed_key.endswith(".parquet")
    assert len(uploaded_objects) == 1

    uploaded = uploaded_objects[0]

    assert uploaded["Bucket"] == ingest.PROCESSED_BUCKET
    assert uploaded["Key"] == processed_key
    assert uploaded["ContentType"] == "application/vnd.apache.parquet"

    parquet_table = pq.read_table(
        io.BytesIO(uploaded["Body"])
    )
    records = parquet_table.to_pylist()

    assert len(records) == 1
    assert records[0]["transaction_id"] == transaction["transaction_id"]
    assert records[0]["account_id"] == transaction["account_id"]
    assert records[0]["amount"] == "60000"
    assert records[0]["risk_level"] == "HIGH"
    assert records[0]["risk_reasons"] == ["HIGH_AMOUNT"]


def test_store_processed_parquet_empty_input(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError(
            "S3 upload should not occur when there are no transactions"
        )

    monkeypatch.setattr(ingest._s3, "put_object", fail_if_called)

    result = ingest.store_processed_parquet(
        transactions=[],
        source_key="uploads/empty.csv",
    )

    assert result is None

import io
import json

import pyarrow.parquet as pq

from fintrust import ingest


def base_transaction():
    return {
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "amount": "1000",
        "currency": "ZAR",
        "source_country": "ZA",
        "destination_country": "ZA",
    }


def test_ingestion_has_no_database_or_dynamodb_dependencies():
    """Ingestion must not persist transactions or risk events."""
    assert not hasattr(ingest, "get_db_connection")
    assert not hasattr(ingest, "insert_transaction")
    assert not hasattr(ingest, "put_risk_event")
    assert not hasattr(ingest, "store_transaction_in_rds")
    assert not hasattr(ingest, "store_risk_event_in_dynamodb")


def test_publish_metrics(monkeypatch):
    published_metrics = []

    def fake_put_metric_data(**kwargs):
        published_metrics.append(kwargs)

    monkeypatch.setattr(
        ingest._cloudwatch,
        "put_metric_data",
        fake_put_metric_data,
    )

    ingest.publish_metrics(
        processed_transactions=10,
        ingestion_errors=2,
    )

    assert len(published_metrics) == 1

    metric_data = published_metrics[0]["MetricData"]

    metric_names = {
        metric["MetricName"]
        for metric in metric_data
    }

    assert "ProcessedTransactions" in metric_names
    assert "IngestionErrors" in metric_names
    assert "HighRiskTransactions" not in metric_names


def test_send_transaction_to_queue(monkeypatch):
    transaction = base_transaction()
    sent_messages = []

    def fake_send_message(**kwargs):
        sent_messages.append(kwargs)
        return {"MessageId": "test-message-id"}

    monkeypatch.setattr(
        ingest._sqs,
        "send_message",
        fake_send_message,
    )

    ingest.send_transaction_to_queue(
        transaction=transaction,
    )

    assert len(sent_messages) == 1

    message = sent_messages[0]

    assert message["QueueUrl"] == ingest.TRANSACTION_QUEUE_URL
    assert message["MessageGroupId"] == transaction["account_id"]
    assert message["MessageDeduplicationId"] == transaction["transaction_id"]

    message_body = json.loads(message["MessageBody"])

    assert message_body["transaction"] == transaction
    assert "risk_level" not in message_body
    assert "risk_reasons" not in message_body


def test_process_valid_transaction_only_queues_transaction(monkeypatch):
    transaction = base_transaction()
    queued_transactions = []

    def fake_send_transaction_to_queue(transaction, upload_id=None):
        queued_transactions.append(transaction)

    monkeypatch.setattr(
        ingest,
        "send_transaction_to_queue",
        fake_send_transaction_to_queue,
    )

    ingest.process_valid_transaction(
        transaction=transaction,
    )

    assert queued_transactions == [transaction]


def test_store_processed_parquet_round_trip(monkeypatch):
    transaction = {
        **base_transaction(),
        "queued_at": "2026-10-10T12:00:00+00:00",
    }

    uploaded_objects = []

    def fake_put_object(**kwargs):
        uploaded_objects.append(kwargs)
        return {}

    monkeypatch.setattr(
        ingest._s3,
        "put_object",
        fake_put_object,
    )

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
    assert records[0]["amount"] == "1000"
    assert records[0]["queued_at"] == transaction["queued_at"]


def test_store_processed_parquet_empty_input(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError(
            "S3 upload should not occur when there are no transactions"
        )

    monkeypatch.setattr(
        ingest._s3,
        "put_object",
        fail_if_called,
    )

    result = ingest.store_processed_parquet(
        transactions=[],
        source_key="uploads/empty.csv",
    )

    assert result is None


def test_lambda_handler_processes_valid_and_invalid_rows(monkeypatch):
    transaction = base_transaction()

    csv_content = (
        "transaction_id,account_id,amount,currency,"
        "source_country,destination_country\n"
        f"{transaction['transaction_id']},"
        f"{transaction['account_id']},"
        "1000,ZAR,ZA,ZA\n"
        "invalid-transaction,invalid-account,1000,ZAR,ZA,ZA\n"
    )

    def fake_get_object(**kwargs):
        return {
            "Body": io.BytesIO(csv_content.encode("utf-8"))
        }

    def fake_validate_transaction(row):
        if row["transaction_id"] == transaction["transaction_id"]:
            return True, []

        return False, ["INVALID_TRANSACTION"]

    uploaded_objects = []
    queued_messages = []
    published_metrics = []

    def fake_put_object(**kwargs):
        uploaded_objects.append(kwargs)
        return {}

    def fake_send_message(**kwargs):
        queued_messages.append(kwargs)
        return {"MessageId": "test-message-id"}

    def fake_publish_metrics(**kwargs):
        published_metrics.append(kwargs)

    monkeypatch.setattr(
        ingest._s3,
        "get_object",
        fake_get_object,
    )

    monkeypatch.setattr(
        ingest._s3,
        "put_object",
        fake_put_object,
    )

    monkeypatch.setattr(
        ingest,
        "validate_transaction",
        fake_validate_transaction,
    )

    monkeypatch.setattr(
        ingest._sqs,
        "send_message",
        fake_send_message,
    )

    monkeypatch.setattr(
        ingest,
        "publish_metrics",
        fake_publish_metrics,
    )

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {
                        "name": "fintrust-prod-raw-transactions"
                    },
                    "object": {
                        "key": "uploads/test-transactions.csv"
                    },
                }
            }
        ]
    }

    response = ingest.lambda_handler(
        event=event,
        context=None,
    )

    result = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert result["total_rows"] == 2
    assert result["valid_rows"] == 1
    assert result["invalid_rows"] == 1

    # Only the valid transaction should enter SQS.
    assert len(queued_messages) == 1

    queued_body = json.loads(
        queued_messages[0]["MessageBody"]
    )

    assert queued_body["transaction"]["transaction_id"] == (
        transaction["transaction_id"]
    )

    # Invalid transaction should be quarantined.
    quarantine_objects = [
        obj
        for obj in uploaded_objects
        if obj["Bucket"] == ingest.QUARANTINE_BUCKET
    ]

    assert len(quarantine_objects) == 1

    quarantine_record = json.loads(
        quarantine_objects[0]["Body"].decode("utf-8")
    )

    assert quarantine_record["validation_errors"] == [
        "INVALID_TRANSACTION"
    ]

    # The valid transaction should be exported as Parquet.
    parquet_objects = [
        obj
        for obj in uploaded_objects
        if obj["Bucket"] == ingest.PROCESSED_BUCKET
    ]

    assert len(parquet_objects) == 1

    assert parquet_objects[0]["ContentType"] == (
        "application/vnd.apache.parquet"
    )

    # Ingestion metrics should reflect validation results.
    assert len(published_metrics) == 1

    assert published_metrics[0] == {
        "processed_transactions": 1,
        "ingestion_errors": 1,
    }
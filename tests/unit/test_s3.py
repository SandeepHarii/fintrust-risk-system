from fintrust import ingest


def test_quarantine_row(aws_resources):
    row = {
        "transaction_id": "TX-TEST-001",
        "account_id": "ACC-001",
        "amount": "1000",
    }

    ingest.quarantine_row(
        row=row,
        row_number=2,
        errors=["Invalid transaction"],
        source_bucket=aws_resources["source_bucket"],
        source_key="test/input.csv",
    )

    response = aws_resources["s3"].get_object(
        Bucket=aws_resources["quarantine_bucket"],
        Key="test/input.csv/row-2-TX-TEST-001.json",
    )

    assert response["ContentType"] == "application/json"

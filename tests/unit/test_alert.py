
import pytest
from botocore.exceptions import ClientError

from fintrust import alert


UPLOAD_ID = "dad74550-013d-4bce-a742-05eae15c2d79"


def make_summary(
    status="COMPLETED",
    total=5,
    valid=5,
    completed=5,
    duplicates=3,
    quarantined=0,
    failure_reason=None,
):
    summary = {
        "upload_id": {"S": UPLOAD_ID},
        "record_type": {"S": "SUMMARY"},
        "status": {"S": status},
        "total_records": {"N": str(total)},
        "valid_records": {"N": str(valid)},
        "completed_records": {"N": str(completed)},
        "duplicate_records": {"N": str(duplicates)},
        "quarantined_records": {"N": str(quarantined)},
    }

    if failure_reason:
        summary["failure_reason"] = {"S": failure_reason}

    return summary


class FakeDynamoDB:
    def __init__(self, summary):
        self.summary = summary
        self.notifications = {}
        self.deleted = []

    def get_item(self, **kwargs):
        return {"Item": self.summary}

    def put_item(self, **kwargs):
        key = (
            kwargs["Item"]["upload_id"]["S"],
            kwargs["Item"]["record_type"]["S"],
        )

        if key in self.notifications:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "Item already exists",
                    }
                },
                "PutItem",
            )

        self.notifications[key] = kwargs["Item"]

    def delete_item(self, **kwargs):
        key = (
            kwargs["Key"]["upload_id"]["S"],
            kwargs["Key"]["record_type"]["S"],
        )

        self.deleted.append(key)
        self.notifications.pop(key, None)


def test_send_high_risk_alert(aws_resources):
    event = {
        "alert_id": "ALERT-001",
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "risk_event_id": "RISK-001",
        "reason": "HIGH_AMOUNT",
        "risk_level": "HIGH",
    }

    result = alert.lambda_handler(event, None)

    assert result["statusCode"] == 200
    assert result["alert_id"] == "ALERT-001"
    assert result["status"] == "SENT"
    assert result["message_id"]


def test_alert_requires_required_fields():
    event = {
        "alert_id": "ALERT-001",
        "transaction_id": "TX-001",
    }

    with pytest.raises(ValueError, match="account_id"):
        alert.lambda_handler(event, None)


def test_upload_completion_email_sent(monkeypatch):
    fake_db = FakeDynamoDB(make_summary())
    sent_emails = []

    monkeypatch.setattr(alert, "_dynamodb", fake_db)
    monkeypatch.setattr(
        alert,
        "_send_email",
        lambda subject, body: (
            sent_emails.append((subject, body)) or "SES-MESSAGE-001"
        ),
    )

    result = alert.lambda_handler(
        {
            "notification_type": "UPLOAD_COMPLETED",
            "upload_id": UPLOAD_ID,
        },
        None,
    )

    assert result["status"] == "SENT"
    assert result["upload_id"] == UPLOAD_ID
    assert result["message_id"] == "SES-MESSAGE-001"
    assert len(sent_emails) == 1

    subject, body = sent_emails[0]

    assert subject == f"FinTrust Upload Completed - {UPLOAD_ID}"
    assert "Total transactions: 5" in body
    assert "New transactions processed: 2" in body
    assert "Duplicate transactions detected: 3" in body
    assert "Failed transactions: 0" in body
    assert "Quarantined transactions: 0" in body
    assert "Completion: 100%" in body


def test_upload_completion_rejects_incomplete_status(monkeypatch):
    fake_db = FakeDynamoDB(make_summary(status="PROCESSING"))
    monkeypatch.setattr(alert, "_dynamodb", fake_db)

    with pytest.raises(ValueError, match="expected COMPLETED"):
        alert.lambda_handler(
            {
                "notification_type": "UPLOAD_COMPLETED",
                "upload_id": UPLOAD_ID,
            },
            None,
        )

    assert not fake_db.notifications


def test_upload_completion_rejects_unfinished_records(monkeypatch):
    fake_db = FakeDynamoDB(
        make_summary(completed=4, valid=5)
    )
    monkeypatch.setattr(alert, "_dynamodb", fake_db)

    with pytest.raises(ValueError, match="not fully processed"):
        alert.lambda_handler(
            {
                "notification_type": "UPLOAD_COMPLETED",
                "upload_id": UPLOAD_ID,
            },
            None,
        )

    assert not fake_db.notifications


def test_upload_completion_email_not_sent_twice(monkeypatch):
    fake_db = FakeDynamoDB(make_summary())
    sent_emails = []

    monkeypatch.setattr(alert, "_dynamodb", fake_db)
    monkeypatch.setattr(
        alert,
        "_send_email",
        lambda subject, body: (
            sent_emails.append(subject) or "SES-MESSAGE-001"
        ),
    )

    event = {
        "notification_type": "UPLOAD_COMPLETED",
        "upload_id": UPLOAD_ID,
    }

    first = alert.lambda_handler(event, None)
    second = alert.lambda_handler(event, None)

    assert first["status"] == "SENT"
    assert second["status"] == "ALREADY_SENT_OR_CLAIMED"
    assert len(sent_emails) == 1


def test_upload_completion_claim_released_when_email_fails(
    monkeypatch,
):
    fake_db = FakeDynamoDB(make_summary())
    monkeypatch.setattr(alert, "_dynamodb", fake_db)

    def failed_email(subject, body):
        raise RuntimeError("SES delivery failed")

    monkeypatch.setattr(alert, "_send_email", failed_email)

    with pytest.raises(RuntimeError, match="SES delivery failed"):
        alert.lambda_handler(
            {
                "notification_type": "UPLOAD_COMPLETED",
                "upload_id": UPLOAD_ID,
            },
            None,
        )

    assert len(fake_db.deleted) == 1
    assert not fake_db.notifications


def test_upload_completion_requires_upload_id():
    with pytest.raises(ValueError, match="upload_id"):
        alert.lambda_handler(
            {"notification_type": "UPLOAD_COMPLETED"},
            None,
        )


def test_upload_failure_email_sent(monkeypatch):
    fake_db = FakeDynamoDB(
        make_summary(
            status="FAILED",
            completed=2,
            failure_reason="Database connection failed",
        )
    )
    sent_emails = []

    monkeypatch.setattr(alert, "_dynamodb", fake_db)
    monkeypatch.setattr(
        alert,
        "_send_email",
        lambda subject, body: (
            sent_emails.append((subject, body)) or "SES-FAILURE-001"
        ),
    )

    result = alert.lambda_handler(
        {
            "notification_type": "UPLOAD_FAILED",
            "upload_id": UPLOAD_ID,
        },
        None,
    )

    assert result["status"] == "SENT"
    assert result["notification_type"] == "UPLOAD_FAILED"
    assert result["upload_id"] == UPLOAD_ID
    assert result["message_id"] == "SES-FAILURE-001"
    assert len(sent_emails) == 1

    subject, body = sent_emails[0]

    assert subject == f"FinTrust Upload Failed - {UPLOAD_ID}"
    assert "Processing status: FAILED" in body
    assert "Transactions processed: 2" in body
    assert "Transactions not completed: 3" in body
    assert "Database connection failed" in body
    assert "could not be completed" in body


def test_upload_failure_rejects_non_failed_status(monkeypatch):
    fake_db = FakeDynamoDB(make_summary(status="PROCESSING"))
    monkeypatch.setattr(alert, "_dynamodb", fake_db)

    with pytest.raises(ValueError, match="expected FAILED"):
        alert.lambda_handler(
            {
                "notification_type": "UPLOAD_FAILED",
                "upload_id": UPLOAD_ID,
            },
            None,
        )

    assert not fake_db.notifications


def test_upload_failure_email_not_sent_twice(monkeypatch):
    fake_db = FakeDynamoDB(
        make_summary(status="FAILED", completed=2)
    )
    sent_emails = []

    monkeypatch.setattr(alert, "_dynamodb", fake_db)
    monkeypatch.setattr(
        alert,
        "_send_email",
        lambda subject, body: (
            sent_emails.append(subject) or "SES-FAILURE-001"
        ),
    )

    event = {
        "notification_type": "UPLOAD_FAILED",
        "upload_id": UPLOAD_ID,
    }

    first = alert.lambda_handler(event, None)
    second = alert.lambda_handler(event, None)

    assert first["status"] == "SENT"
    assert second["status"] == "ALREADY_SENT_OR_CLAIMED"
    assert len(sent_emails) == 1


def test_upload_failure_claim_released_when_email_fails(monkeypatch):
    fake_db = FakeDynamoDB(
        make_summary(status="FAILED", completed=2)
    )
    monkeypatch.setattr(alert, "_dynamodb", fake_db)

    def failed_email(subject, body):
        raise RuntimeError("SES delivery failed")

    monkeypatch.setattr(alert, "_send_email", failed_email)

    with pytest.raises(RuntimeError, match="SES delivery failed"):
        alert.lambda_handler(
            {
                "notification_type": "UPLOAD_FAILED",
                "upload_id": UPLOAD_ID,
            },
            None,
        )

    assert len(fake_db.deleted) == 1
    assert not fake_db.notifications


def test_upload_failure_requires_upload_id():
    with pytest.raises(ValueError, match="upload_id"):
        alert.lambda_handler(
            {"notification_type": "UPLOAD_FAILED"},
            None,
        )
from fintrust import alert


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

    try:
        alert.lambda_handler(event, None)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "account_id" in str(exc)
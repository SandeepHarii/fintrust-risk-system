from fintrust import dynamo


def test_put_and_get_risk_event(aws_resources):
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


def test_get_account_risk_events(aws_resources):
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

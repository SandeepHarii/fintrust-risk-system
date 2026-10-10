from datetime import datetime, timezone

from fintrust.score import calculate_risk_score


def base_transaction():
    return {
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "amount": "1000",
        "source_country": "ZA",
        "destination_country": "ZA",
        "tx_date": "2026-10-01T10:00:00+00:00",
    }


def test_low_risk_transaction():
    score, risk_level, reasons = calculate_risk_score(
        base_transaction(),
        [base_transaction()],
    )

    assert score == 0
    assert risk_level == "LOW"
    assert reasons == []


def test_high_amount_scores_high():
    transaction = base_transaction()
    transaction["amount"] = "50001"

    score, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score == 30
    assert risk_level == "HIGH"
    assert reasons == ["HIGH_AMOUNT"]


def test_cross_border_scores_low():
    transaction = base_transaction()
    transaction["destination_country"] = "GB"

    score, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score == 20
    assert risk_level == "LOW"
    assert reasons == ["CROSS_BORDER"]


def test_high_velocity_scores_high():
    transaction = base_transaction()
    transactions = []

    for index in range(11):
        transactions.append(
            {
                **transaction,
                "transaction_id": (
                    f"550e8400-e29b-41d4-a716-4466554400{index:02d}"
                ),
                "tx_date": datetime(
                    2026, 10, 1, 10, index, tzinfo=timezone.utc
                ).isoformat(),
            }
        )

    current_transaction = transactions[-1]
    score, risk_level, reasons = calculate_risk_score(
        current_transaction,
        transactions,
    )

    assert score == 40
    assert risk_level == "HIGH"
    assert reasons == ["HIGH_VELOCITY"]


def test_high_amount_and_cross_border_is_high():
    transaction = base_transaction()
    transaction["amount"] = "75000"
    transaction["destination_country"] = "GB"

    score, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score == 50
    assert risk_level == "HIGH"
    assert "HIGH_AMOUNT" in reasons
    assert "CROSS_BORDER" in reasons


def test_high_amount_and_velocity_is_high():
    transaction = base_transaction()
    transaction["amount"] = "75000"
    transactions = []

    for index in range(11):
        transactions.append(
            {
                **transaction,
                "transaction_id": (
                    f"650e8400-e29b-41d4-a716-4466554400{index:02d}"
                ),
                "tx_date": datetime(
                    2026, 10, 1, 10, index, tzinfo=timezone.utc
                ).isoformat(),
            }
        )

    current_transaction = transactions[-1]
    score, risk_level, reasons = calculate_risk_score(
        current_transaction,
        transactions,
    )

    assert score == 70
    assert risk_level == "HIGH"
    assert "HIGH_AMOUNT" in reasons
    assert "HIGH_VELOCITY" in reasons


def test_all_three_rules_score_high():
    transaction = base_transaction()
    transaction["amount"] = "75000"
    transaction["destination_country"] = "GB"
    transactions = []

    for index in range(11):
        transactions.append(
            {
                **transaction,
                "transaction_id": (
                    f"750e8400-e29b-41d4-a716-4466554400{index:02d}"
                ),
                "tx_date": datetime(
                    2026, 10, 1, 10, index, tzinfo=timezone.utc
                ).isoformat(),
            }
        )

    current_transaction = transactions[-1]
    score, risk_level, reasons = calculate_risk_score(
        current_transaction,
        transactions,
    )

    assert score == 90
    assert risk_level == "HIGH"
    assert "HIGH_AMOUNT" in reasons
    assert "HIGH_VELOCITY" in reasons
    assert "CROSS_BORDER" in reasons


def test_invalid_amount_returns_low_score():
    transaction = base_transaction()
    transaction["amount"] = "not-a-number"

    score, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score == 0
    assert risk_level == "LOW"
    assert reasons == ["INVALID_AMOUNT"]
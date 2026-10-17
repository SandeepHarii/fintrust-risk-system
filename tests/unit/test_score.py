from contextlib import nullcontext
from datetime import datetime, timezone

import pytest

from fintrust import score
from fintrust.score import calculate_risk_score


def base_transaction():
    return {
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "amount": "1000",
        "currency": "ZAR",
        "source_country": "ZA",
        "destination_country": "ZA",
        "transaction_type": "PAYMENT",
        "tx_date": "2026-10-01T10:00:00+00:00",
    }


def test_low_risk_transaction():
    score_value, risk_level, reasons = calculate_risk_score(
        base_transaction(),
        [base_transaction()],
    )

    assert score_value == 0
    assert risk_level == "LOW"
    assert reasons == []


def test_high_amount_scores_high():
    transaction = base_transaction()
    transaction["amount"] = "50001"

    score_value, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score_value == 30
    assert risk_level == "HIGH"
    assert reasons == ["HIGH_AMOUNT"]


def test_cross_border_scores_low():
    transaction = base_transaction()
    transaction["destination_country"] = "GB"

    score_value, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score_value == 20
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

    score_value, risk_level, reasons = calculate_risk_score(
        current_transaction,
        transactions,
    )

    assert score_value == 40
    assert risk_level == "HIGH"
    assert reasons == ["HIGH_VELOCITY"]


def test_high_amount_and_cross_border_is_high():
    transaction = base_transaction()
    transaction["amount"] = "75000"
    transaction["destination_country"] = "GB"

    score_value, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score_value == 50
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

    score_value, risk_level, reasons = calculate_risk_score(
        current_transaction,
        transactions,
    )

    assert score_value == 70
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

    score_value, risk_level, reasons = calculate_risk_score(
        current_transaction,
        transactions,
    )

    assert score_value == 90
    assert risk_level == "HIGH"
    assert "HIGH_AMOUNT" in reasons
    assert "HIGH_VELOCITY" in reasons
    assert "CROSS_BORDER" in reasons


def test_invalid_amount_returns_low_score():
    transaction = base_transaction()
    transaction["amount"] = "not-a-number"

    score_value, risk_level, reasons = calculate_risk_score(
        transaction,
        [transaction],
    )

    assert score_value == 0
    assert risk_level == "LOW"
    assert reasons == ["INVALID_AMOUNT"]


def test_duplicate_transaction_reuses_existing_risk_event(monkeypatch):
    transaction = base_transaction()
    connection = object()

    existing_event = {
        "risk_event_id": "existing-risk-event-id",
        "risk_reasons": [],
        "risk_level": "LOW",
        "alert_id": None,
        "alert_status": None,
    }

    scored = []
    persisted = []
    dynamo_events = []

    monkeypatch.setattr(
        score,
        "get_db_connection",
        lambda: nullcontext(connection),
    )

    monkeypatch.setattr(
        score,
        "insert_transaction_if_missing",
        lambda **kwargs: False,
    )

    monkeypatch.setattr(
        score,
        "get_existing_risk_event",
        lambda **kwargs: existing_event,
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "Existing duplicate should not be recalculated"
        )

    monkeypatch.setattr(
        score,
        "get_account_transactions",
        fail_if_called,
    )

    monkeypatch.setattr(
        score,
        "calculate_risk_score",
        fail_if_called,
    )

    monkeypatch.setattr(
        score,
        "update_transaction_risk",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        score,
        "mark_transaction_scored",
        lambda **kwargs: scored.append(kwargs),
    )

    monkeypatch.setattr(
        score,
        "mark_transaction_persisted",
        lambda **kwargs: persisted.append(kwargs),
    )

    monkeypatch.setattr(
        score,
        "put_risk_event",
        lambda **kwargs: dynamo_events.append(kwargs),
    )

    result = score.process_transaction(
        transaction=transaction,
        upload_id="test-upload-id",
    )

    assert result["duplicate_transaction"] is True
    assert result["risk_level"] == "LOW"
    assert result["risk_score"] == 0
    assert result["risk_event_id"] == "existing-risk-event-id"

    assert len(scored) == 1
    assert scored[0]["duplicate_transaction"] is True

    assert len(persisted) == 1
    assert len(dynamo_events) == 1


def test_duplicate_without_existing_risk_event_recovers(monkeypatch):
    transaction = base_transaction()
    connection = object()

    scored = []
    persisted = []
    inserted_events = []

    monkeypatch.setattr(
        score,
        "get_db_connection",
        lambda: nullcontext(connection),
    )

    monkeypatch.setattr(
        score,
        "insert_transaction_if_missing",
        lambda **kwargs: False,
    )

    monkeypatch.setattr(
        score,
        "get_existing_risk_event",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        score,
        "get_account_transactions",
        lambda **kwargs: [transaction],
    )

    monkeypatch.setattr(
        score,
        "calculate_risk_score",
        lambda **kwargs: (0, "LOW", []),
    )

    monkeypatch.setattr(
        score,
        "update_transaction_risk",
        lambda **kwargs: None,
    )

    def fake_insert_risk_event(**kwargs):
        inserted_events.append(kwargs)
        return "recovered-risk-event-id"

    monkeypatch.setattr(
        score,
        "insert_postgres_risk_event",
        fake_insert_risk_event,
    )

    monkeypatch.setattr(
        score,
        "mark_transaction_scored",
        lambda **kwargs: scored.append(kwargs),
    )

    monkeypatch.setattr(
        score,
        "mark_transaction_persisted",
        lambda **kwargs: persisted.append(kwargs),
    )

    monkeypatch.setattr(
        score,
        "put_risk_event",
        lambda **kwargs: None,
    )

    result = score.process_transaction(
        transaction=transaction,
        upload_id="recovery-upload-id",
    )

    assert result["duplicate_transaction"] is True
    assert result["risk_level"] == "LOW"
    assert result["risk_event_id"] == "recovered-risk-event-id"

    assert len(inserted_events) == 1
    assert len(scored) == 1
    assert scored[0]["duplicate_transaction"] is True

    assert len(persisted) == 1


def test_conflicting_duplicate_is_skipped(monkeypatch):
    transaction = base_transaction()
    scored = []
    persisted = []
    dynamo_events = []

    def raise_duplicate_conflict(**kwargs):
        raise score.DuplicateTransactionConflict(
            "Transaction ID already exists with different details"
        )

    monkeypatch.setattr(
        score,
        "get_db_connection",
        lambda: nullcontext(object()),
    )

    monkeypatch.setattr(
        score,
        "insert_transaction_if_missing",
        raise_duplicate_conflict,
    )

    monkeypatch.setattr(
        score,
        "mark_transaction_scored",
        lambda **kwargs: scored.append(kwargs),
    )

    monkeypatch.setattr(
        score,
        "mark_transaction_persisted",
        lambda **kwargs: persisted.append(kwargs),
    )

    monkeypatch.setattr(
        score,
        "put_risk_event",
        lambda **kwargs: dynamo_events.append(kwargs),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "Conflicting duplicate must not modify existing risk data"
        )

    monkeypatch.setattr(
        score,
        "update_transaction_risk",
        fail_if_called,
    )

    monkeypatch.setattr(
        score,
        "insert_postgres_risk_event",
        fail_if_called,
    )

    monkeypatch.setattr(
        score,
        "get_existing_risk_event",
        fail_if_called,
    )

    result = score.process_transaction(
        transaction=transaction,
        upload_id="duplicate-test-upload",
    )

    assert result["transaction_id"] == transaction["transaction_id"]
    assert result["duplicate_transaction"] is True
    assert result["processing_status"] == "DUPLICATE_SKIPPED"
    assert result["risk_score"] is None
    assert result["risk_level"] is None
    assert result["risk_event_id"] is None

    assert len(scored) == 1
    assert scored[0] == {
        "upload_id": "duplicate-test-upload",
        "transaction_id": transaction["transaction_id"],
        "duplicate_transaction": True,
    }

    assert len(persisted) == 1
    assert persisted[0] == {
        "upload_id": "duplicate-test-upload",
        "transaction_id": transaction["transaction_id"],
    }

    assert dynamo_events == []


def test_conflicting_duplicate_without_upload_id_raises(monkeypatch):
    transaction = base_transaction()

    monkeypatch.setattr(
        score,
        "get_db_connection",
        lambda: nullcontext(object()),
    )

    def raise_duplicate_conflict(**kwargs):
        raise score.DuplicateTransactionConflict(
            "Transaction ID already exists with different details"
        )

    monkeypatch.setattr(
        score,
        "insert_transaction_if_missing",
        raise_duplicate_conflict,
    )

    with pytest.raises(score.DuplicateTransactionConflict):
        score.process_transaction(
            transaction=transaction,
            upload_id=None,
        )


def test_scoring_marker_is_written_after_postgres_commit(monkeypatch):
    transaction = base_transaction()
    events = []

    class FakeDatabaseContext:
        def __enter__(self):
            events.append("database_entered")
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            events.append("database_committed")
            return False

    monkeypatch.setattr(
        score,
        "get_db_connection",
        lambda: FakeDatabaseContext(),
    )

    monkeypatch.setattr(
        score,
        "insert_transaction_if_missing",
        lambda **kwargs: True,
    )

    monkeypatch.setattr(
        score,
        "get_existing_risk_event",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        score,
        "get_account_transactions",
        lambda **kwargs: [transaction],
    )

    monkeypatch.setattr(
        score,
        "calculate_risk_score",
        lambda **kwargs: (0, "LOW", []),
    )

    monkeypatch.setattr(
        score,
        "update_transaction_risk",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        score,
        "insert_postgres_risk_event",
        lambda **kwargs: "test-risk-event-id",
    )

    def fake_mark_scored(**kwargs):
        assert "database_committed" in events
        events.append("scoring_marked")

    monkeypatch.setattr(
        score,
        "mark_transaction_scored",
        fake_mark_scored,
    )

    monkeypatch.setattr(
        score,
        "put_risk_event",
        lambda **kwargs: events.append("dynamo_persisted"),
    )

    monkeypatch.setattr(
        score,
        "mark_transaction_persisted",
        lambda **kwargs: events.append("persistence_marked"),
    )

    result = score.process_transaction(
        transaction=transaction,
        upload_id="commit-order-test",
    )

    assert result["duplicate_transaction"] is False

    assert events.index("database_committed") < events.index(
        "scoring_marked"
    )

    assert events.index("scoring_marked") < events.index(
        "dynamo_persisted"
    )

    assert events.index("dynamo_persisted") < events.index(
        "persistence_marked"
    )

from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from fintrust.score import (
    insert_transaction_if_missing,
    process_transaction,
)


def base_transaction():
    return {
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "tx_date": "2026-10-01T10:00:00+00:00",
        "amount": "75000.00",
        "currency": "ZAR",
        "transaction_type": "PAYMENT",
        "source_country": "ZA",
        "destination_country": "GB",
    }


class FakeCursor:
    def __init__(self, existing_row):
        self.existing_row = existing_row
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.existing_row


class FakeConnection:
    def __init__(self, existing_row):
        self.fake_cursor = FakeCursor(existing_row)

    def cursor(self):
        return self.fake_cursor


@pytest.fixture
def mocked_score_dependencies():
    names = [
        "get_db_connection",
        "insert_transaction_if_missing",
        "get_account_transactions",
        "calculate_risk_score",
        "get_existing_risk_event",
        "update_transaction_risk",
        "insert_postgres_risk_event",
        "create_alert",
        "put_risk_event",
        "invoke_alert_lambda",
        "update_alert_status",
    ]

    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(
                patch(f"fintrust.score.{name}")
            )
            for name in names
        }

        mocks["get_db_connection"].return_value = nullcontext(
            object()
        )

        mocks["get_account_transactions"].return_value = []

        mocks["calculate_risk_score"].return_value = (
            70,
            "HIGH",
            ["HIGH_AMOUNT", "CROSS_BORDER"],
        )

        mocks["get_existing_risk_event"].return_value = None

        mocks["insert_postgres_risk_event"].return_value = (
            "risk-event-123"
        )

        mocks["create_alert"].return_value = "alert-123"

        yield mocks


def existing_transaction_row():
    return (
        "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
        Decimal("75000.00"),
        "ZAR",
        "PAYMENT",
        "ZA",
        "GB",
    )


def existing_risk_event(
    alert_id="alert-123",
    alert_status="SENT",
):
    return {
        "risk_event_id": "risk-event-123",
        "risk_reasons": ["HIGH_AMOUNT", "CROSS_BORDER"],
        "risk_level": "HIGH",
        "alert_id": alert_id,
        "alert_status": alert_status,
    }


def test_identical_existing_transaction_is_accepted():
    transaction = base_transaction()

    conn = FakeConnection(existing_transaction_row())

    insert_transaction_if_missing(
        conn=conn,
        transaction=transaction,
    )

    assert len(conn.fake_cursor.executed) == 2


def test_existing_transaction_with_different_amount_is_rejected():
    transaction = base_transaction()
    transaction["amount"] = "90000.00"

    conn = FakeConnection(existing_transaction_row())

    with pytest.raises(
        ValueError,
        match="different transaction details",
    ):
        insert_transaction_if_missing(
            conn=conn,
            transaction=transaction,
        )


def test_new_transaction_persists_risk_event_and_dynamodb(
    mocked_score_dependencies,
):
    mocks = mocked_score_dependencies
    transaction = base_transaction()

    result = process_transaction(transaction)

    mocks["insert_transaction_if_missing"].assert_called_once()

    mocks["insert_postgres_risk_event"].assert_called_once_with(
        conn=mocks["get_db_connection"].return_value.__enter__(),
        transaction=transaction,
        risk_level="HIGH",
        risk_reasons=["HIGH_AMOUNT", "CROSS_BORDER"],
    )

    mocks["put_risk_event"].assert_called_once_with(
        account_id=transaction["account_id"],
        transaction_id=transaction["transaction_id"],
        transaction_timestamp=transaction["tx_date"],
        risk_event={
            "risk_score": 70,
            "risk_level": "HIGH",
            "risk_reasons": ["HIGH_AMOUNT", "CROSS_BORDER"],
        },
    )

    mocks["invoke_alert_lambda"].assert_called_once()

    mocks["update_alert_status"].assert_called_once_with(
        conn=mocks["get_db_connection"].return_value.__enter__(),
        alert_id="alert-123",
        status="SENT",
    )

    assert result["risk_event_id"] == "risk-event-123"
    assert result["alert_id"] == "alert-123"
    assert result["risk_level"] == "HIGH"


def test_existing_risk_event_with_missing_alert_is_recovered(
    mocked_score_dependencies,
):
    mocks = mocked_score_dependencies
    transaction = base_transaction()

    mocks["get_existing_risk_event"].return_value = (
        existing_risk_event(
            alert_id=None,
            alert_status=None,
        )
    )

    result = process_transaction(transaction)

    mocks["insert_postgres_risk_event"].assert_not_called()

    mocks["create_alert"].assert_called_once_with(
        conn=mocks["get_db_connection"].return_value.__enter__(),
        transaction=transaction,
        risk_event_id="risk-event-123",
    )

    mocks["invoke_alert_lambda"].assert_called_once()

    mocks["update_alert_status"].assert_called_once()

    assert result["risk_event_id"] == "risk-event-123"
    assert result["alert_id"] == "alert-123"


@pytest.mark.parametrize(
    "alert_status",
    ["SENT", "RESOLVED"],
)
def test_sent_or_resolved_alert_is_not_resent(
    mocked_score_dependencies,
    alert_status,
):
    mocks = mocked_score_dependencies
    transaction = base_transaction()

    mocks["get_existing_risk_event"].return_value = (
        existing_risk_event(
            alert_id="alert-123",
            alert_status=alert_status,
        )
    )

    result = process_transaction(transaction)

    mocks["insert_postgres_risk_event"].assert_not_called()

    mocks["invoke_alert_lambda"].assert_not_called()

    mocks["update_alert_status"].assert_not_called()

    mocks["put_risk_event"].assert_called_once()

    assert result["risk_event_id"] == "risk-event-123"


def test_failed_alert_is_retried(
    mocked_score_dependencies,
):
    mocks = mocked_score_dependencies
    transaction = base_transaction()

    mocks["get_existing_risk_event"].return_value = (
        existing_risk_event(
            alert_id="alert-123",
            alert_status="FAILED",
        )
    )

    result = process_transaction(transaction)

    mocks["insert_postgres_risk_event"].assert_not_called()

    mocks["invoke_alert_lambda"].assert_called_once()

    mocks["update_alert_status"].assert_called_once_with(
        conn=mocks["get_db_connection"].return_value.__enter__(),
        alert_id="alert-123",
        status="SENT",
    )

    assert result["alert_id"] == "alert-123"
    assert result["risk_level"] == "HIGH"

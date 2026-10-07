from fintrust.validators import validate_transaction


def valid_transaction():
    return {
        "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8",
        "tx_date": "2026-09-29T10:00:00+00:00",
        "amount": "1000.00",
        "currency": "ZAR",
        "transaction_type": "PAYMENT",
        "source_country": "ZA",
        "destination_country": "ZA",
    }


def test_valid_transaction():
    is_valid, errors = validate_transaction(valid_transaction())

    assert is_valid is True
    assert errors == []


def test_missing_required_field():
    transaction = valid_transaction()
    del transaction["amount"]

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert "Missing required field: amount" in errors


def test_invalid_uuid():
    transaction = valid_transaction()
    transaction["transaction_id"] = "not-a-uuid"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert "transaction_id must be a valid UUID." in errors


def test_invalid_amount():
    transaction = valid_transaction()
    transaction["amount"] = "-100"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert "amount must be greater than zero." in errors


def test_invalid_currency():
    transaction = valid_transaction()
    transaction["currency"] = "zar"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert "currency must be exactly 3 uppercase letters." in errors


def test_invalid_transaction_type():
    transaction = valid_transaction()
    transaction["transaction_type"] = "INVALID"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert "transaction_type must be one of:" in errors[0]


def test_invalid_country_code():
    transaction = valid_transaction()
    transaction["source_country"] = "ZAF"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert "source_country must be exactly 2 uppercase letters." in errors
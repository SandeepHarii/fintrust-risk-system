
import pytest
import pycountry

from fintrust.validators import validate_transaction, MAX_AMOUNT


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


# ------------------------------------------------------------
# BASIC VALIDATION
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# TIMESTAMP VALIDATION
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-29T10:00:00",
        "not-a-date",
        "",
        "2026-13-29T10:00:00+00:00",
        "2026-09-29T25:00:00+00:00",
    ],
)
def test_invalid_timestamp(timestamp):
    transaction = valid_transaction()
    transaction["tx_date"] = timestamp

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any("tx_date" in error for error in errors)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-29T10:00:00+00:00",
        "2026-09-29T10:00:00+02:00",
        "2026-09-29T08:00:00Z",
    ],
)
def test_valid_timezone_aware_timestamp(timestamp):
    transaction = valid_transaction()
    transaction["tx_date"] = timestamp

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is True
    assert errors == []


# ------------------------------------------------------------
# AMOUNT VALIDATION
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "amount",
    [
        "-100",
        "0",
        "0.00",
        "NaN",
        "Infinity",
        "-Infinity",
        "not-a-number",
        "100.123",
        "10000000000000000.00",
    ],
)
def test_invalid_amount(amount):
    transaction = valid_transaction()
    transaction["amount"] = amount

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any(error.startswith("amount") for error in errors)


@pytest.mark.parametrize(
    "amount",
    [
        "0.01",
        "1",
        "1000.00",
        "9999999999999999.99",
        "100.230",
    ],
)
def test_valid_amount(amount):
    transaction = valid_transaction()
    transaction["amount"] = amount

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is True
    assert errors == []


def test_maximum_database_amount():
    transaction = valid_transaction()
    transaction["amount"] = str(MAX_AMOUNT)

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is True
    assert errors == []


# ------------------------------------------------------------
# CURRENCY VALIDATION
# ------------------------------------------------------------

def test_invalid_currency():
    transaction = valid_transaction()
    transaction["currency"] = "zar"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any("currency" in error for error in errors)


@pytest.mark.parametrize(
    "currency",
    [
        "ZZZ",
        "ABC",
        "123",
        "US",
        "USDD",
        "",
        " ZAR",
        "ZAR ",
        "€€€",
    ],
)
def test_unrecognised_currency_codes(currency):
    transaction = valid_transaction()
    transaction["currency"] = currency

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any("currency" in error for error in errors)


@pytest.mark.parametrize(
    "currency",
    sorted(currency.alpha_3 for currency in pycountry.currencies),
)
def test_all_recognised_iso_currency_codes(currency):
    transaction = valid_transaction()
    transaction["currency"] = currency

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is True
    assert errors == []


def test_withdrawn_currency_rejected():
    transaction = valid_transaction()
    transaction["currency"] = "DEM"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any("currency" in error for error in errors)


# ------------------------------------------------------------
# TRANSACTION TYPE VALIDATION
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "transaction_type",
    [
        "PAYMENT",
        "TRANSFER",
        "WITHDRAWAL",
        "DEPOSIT",
        "PURCHASE",
    ],
)
def test_all_supported_transaction_types(transaction_type):
    transaction = valid_transaction()
    transaction["transaction_type"] = transaction_type

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is True
    assert errors == []


@pytest.mark.parametrize(
    "transaction_type",
    [
        "INVALID",
        "payment",
        "TRANSFER ",
        "",
        "REFUND",
        "CASH",
        None,
    ],
)
def test_invalid_transaction_types(transaction_type):
    transaction = valid_transaction()
    transaction["transaction_type"] = transaction_type

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any("transaction_type" in error for error in errors)


# ------------------------------------------------------------
# COUNTRY VALIDATION
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "country",
    [
        "ZAF",
        "ZZ",
        "XX",
        "123",
        "zA",
        "",
        " ZA",
        "ZA ",
        "€€",
    ],
)
def test_invalid_country_codes(country):
    transaction = valid_transaction()
    transaction["source_country"] = country

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any("source_country" in error for error in errors)


@pytest.mark.parametrize(
    "country",
    sorted(country.alpha_2 for country in pycountry.countries),
)
def test_all_recognised_iso_country_codes(country):
    transaction = valid_transaction()
    transaction["source_country"] = country
    transaction["destination_country"] = country

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is True
    assert errors == []


def test_invalid_destination_country():
    transaction = valid_transaction()
    transaction["destination_country"] = "ZZ"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert any("destination_country" in error for error in errors)


# ------------------------------------------------------------
# MULTIPLE INVALID FIELDS
# ------------------------------------------------------------

def test_multiple_invalid_fields():
    transaction = valid_transaction()

    transaction["transaction_id"] = "invalid"
    transaction["amount"] = "-100"
    transaction["currency"] = "ZZZ"
    transaction["source_country"] = "ZZ"
    transaction["transaction_type"] = "INVALID"

    is_valid, errors = validate_transaction(transaction)

    assert is_valid is False
    assert len(errors) >= 5
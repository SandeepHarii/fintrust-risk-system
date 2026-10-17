
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import pycountry


REQUIRED_FIELDS = {
    "transaction_id",
    "account_id",
    "tx_date",
    "amount",
    "currency",
    "transaction_type",
    "source_country",
    "destination_country",
}

ALLOWED_TRANSACTION_TYPES = {
    "PAYMENT",
    "TRANSFER",
    "WITHDRAWAL",
    "DEPOSIT",
    "PURCHASE",
}

MAX_AMOUNT = Decimal("9999999999999999.99")
TWO_DECIMAL_PLACES = Decimal("0.01")


def validate_transaction(
    transaction: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Validate a transaction against the FinTrust PostgreSQL schema."""

    errors: list[str] = []

    if not isinstance(transaction, dict):
        return False, ["Transaction must be a dictionary."]

    # Required fields
    missing_fields = REQUIRED_FIELDS - transaction.keys()

    if missing_fields:
        errors.extend(
            f"Missing required field: {field}"
            for field in sorted(missing_fields)
        )
        return False, errors

    # UUID validation
    for field in ("transaction_id", "account_id"):
        try:
            UUID(str(transaction[field]))
        except (ValueError, TypeError, AttributeError):
            errors.append(f"{field} must be a valid UUID.")

    # ISO 8601 timestamp validation
    try:
        timestamp = str(transaction["tx_date"])

        # Support the ISO 8601 UTC suffix.
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"

        parsed_timestamp = datetime.fromisoformat(timestamp)

        if (
            parsed_timestamp.tzinfo is None
            or parsed_timestamp.utcoffset() is None
        ):
            errors.append(
                "tx_date must include a valid timezone offset."
            )

    except (ValueError, TypeError, OverflowError):
        errors.append(
            "tx_date must be a valid ISO 8601 timestamp."
        )

    # Amount validation: PostgreSQL NUMERIC(18, 2)
    try:
        amount = Decimal(str(transaction["amount"]))

        if not amount.is_finite():
            errors.append("amount must be a finite number.")

        elif amount <= 0:
            errors.append("amount must be greater than zero.")

        elif amount > MAX_AMOUNT:
            errors.append(
                "amount exceeds the maximum supported value "
                "of 9999999999999999.99."
            )

        elif amount != amount.quantize(TWO_DECIMAL_PLACES):
            errors.append(
                "amount must not have more than 2 decimal places."
            )

    except (InvalidOperation, TypeError, ValueError):
        errors.append("amount must be a valid number.")

    # ISO 4217 currency validation
    currency = transaction["currency"]

    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
        or currency != currency.upper()
        or pycountry.currencies.get(alpha_3=currency) is None
    ):
        errors.append(
            "currency must be a recognised ISO 4217 currency code."
        )

    # Transaction type validation
    transaction_type = transaction["transaction_type"]

    if (
        not isinstance(transaction_type, str)
        or transaction_type not in ALLOWED_TRANSACTION_TYPES
    ):
        errors.append(
            "transaction_type must be one of: "
            + ", ".join(sorted(ALLOWED_TRANSACTION_TYPES))
            + "."
        )

    # ISO 3166-1 alpha-2 country validation
    for field in ("source_country", "destination_country"):
        country = transaction[field]

        if (
            not isinstance(country, str)
            or len(country) != 2
            or not country.isascii()
            or not country.isalpha()
            or country != country.upper()
            or pycountry.countries.get(alpha_2=country) is None
        ):
            errors.append(
                f"{field} must be a recognised ISO 3166-1 "
                "alpha-2 country code."
            )

    return not errors, errors
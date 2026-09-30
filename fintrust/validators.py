import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID


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

CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")


def validate_transaction(transaction: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a transaction against the FinTrust PostgreSQL schema."""

    errors: list[str] = []

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

    # Timestamp validation
    try:
        datetime.fromisoformat(str(transaction["tx_date"]))
    except (ValueError, TypeError):
        errors.append("tx_date must be a valid ISO 8601 timestamp.")

    # Amount validation
    try:
        amount = Decimal(str(transaction["amount"]))

        if amount <= 0:
            errors.append("amount must be greater than zero.")

    except (InvalidOperation, TypeError, ValueError):
        errors.append("amount must be a valid number.")

    # Currency validation
    currency = str(transaction["currency"])

    if not CURRENCY_PATTERN.fullmatch(currency):
        errors.append("currency must be exactly 3 uppercase letters.")

    # Transaction type validation
    transaction_type = str(transaction["transaction_type"])

    if transaction_type not in ALLOWED_TRANSACTION_TYPES:
        errors.append(
            "transaction_type must be one of: "
            + ", ".join(sorted(ALLOWED_TRANSACTION_TYPES))
            + "."
        )

    # Country validation
    for field in ("source_country", "destination_country"):
        country = str(transaction[field])

        if not COUNTRY_PATTERN.fullmatch(country):
            errors.append(
                f"{field} must be exactly 2 uppercase letters."
            )

    return not errors, errors
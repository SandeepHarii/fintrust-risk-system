from decimal import Decimal, InvalidOperation
from typing import Any


REQUIRED_FIELDS = {
    "transaction_id",
    "account_id",
    "transaction_timestamp",
    "amount",
    "currency",
    "country",
}


def validate_transaction(transaction: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate the minimum required transaction fields."""

    errors: list[str] = []

    missing_fields = REQUIRED_FIELDS - transaction.keys()

    if missing_fields:
        errors.extend(
            f"Missing required field: {field}"
            for field in sorted(missing_fields)
        )

    if "amount" in transaction:
        try:
            amount = Decimal(str(transaction["amount"]))

            if amount <= 0:
                errors.append("Amount must be greater than zero.")

        except (InvalidOperation, TypeError, ValueError):
            errors.append("Amount must be a valid number.")

    for field in ("transaction_id", "account_id", "currency", "country"):
        if field in transaction and not str(transaction[field]).strip():
            errors.append(f"{field} cannot be empty.")

    return not errors, errors
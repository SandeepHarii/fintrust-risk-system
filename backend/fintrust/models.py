from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


TransactionType = Literal[
    "PAYMENT",
    "TRANSFER",
    "WITHDRAWAL",
    "DEPOSIT",
    "PURCHASE",
]

RiskLevel = Literal[
    "LOW",
    "MEDIUM",
    "HIGH",
]


class Transaction(BaseModel):
    """FinTrust transaction data model."""

    transaction_id: UUID
    account_id: UUID
    tx_date: datetime
    amount: Decimal
    currency: str = Field(
        default="ZAR",
        min_length=3,
        max_length=3,
    )
    transaction_type: TransactionType
    source_country: str = Field(
        min_length=2,
        max_length=2,
    )
    destination_country: str = Field(
        min_length=2,
        max_length=2,
    )
    risk_flag: RiskLevel | None = None


class RiskScore(BaseModel):
    """Final risk scoring result for a transaction."""

    transaction_id: UUID
    account_id: UUID
    risk_score: int = Field(
        ge=0,
        le=90,
    )
    risk_level: RiskLevel
    risk_reasons: list[str] = Field(default_factory=list)
    risk_event_id: UUID
    alert_id: UUID | None = None
-- FinTrust Transaction Insights and Risk Monitoring System
-- PostgreSQL Core Transaction Ledger
-- Schema: 3NF

BEGIN;

-- ============================================================
-- ACCOUNTS
-- ============================================================

CREATE TABLE accounts (
    account_id UUID PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL UNIQUE,
    account_holder_name VARCHAR(150) NOT NULL,
    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_accounts_status
        CHECK (account_status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

-- ============================================================
-- TRANSACTIONS
-- ============================================================

CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    tx_date TIMESTAMPTZ NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'ZAR',
    transaction_type VARCHAR(30) NOT NULL,
    source_country CHAR(2) NOT NULL,
    destination_country CHAR(2) NOT NULL,
    risk_flag VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_transactions_account
        FOREIGN KEY (account_id)
        REFERENCES accounts(account_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_transactions_amount
        CHECK (amount > 0),

    CONSTRAINT chk_transactions_currency
        CHECK (currency ~ '^[A-Z]{3}$'),

    CONSTRAINT chk_transactions_type
        CHECK (
            transaction_type IN (
                'PAYMENT',
                'TRANSFER',
                'WITHDRAWAL',
                'DEPOSIT',
                'PURCHASE'
            )
        ),

    CONSTRAINT chk_transactions_source_country
        CHECK (source_country ~ '^[A-Z]{2}$'),

    CONSTRAINT chk_transactions_destination_country
        CHECK (destination_country ~ '^[A-Z]{2}$'),

    CONSTRAINT chk_transactions_risk_flag
        CHECK (
            risk_flag IS NULL
            OR risk_flag IN ('LOW', 'MEDIUM', 'HIGH')
        )
);

-- ============================================================
-- RISK EVENTS
-- ============================================================

CREATE TABLE risk_events (
    risk_event_id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    transaction_id UUID NOT NULL,
    reason VARCHAR(255) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_risk_events_account
        FOREIGN KEY (account_id)
        REFERENCES accounts(account_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_risk_events_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(transaction_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_risk_events_level
        CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH'))
);

-- ============================================================
-- ALERTS
-- ============================================================

CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    transaction_id UUID NOT NULL,
    risk_event_id UUID NOT NULL,
    alert_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    sent_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,

    CONSTRAINT fk_alerts_account
        FOREIGN KEY (account_id)
        REFERENCES accounts(account_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_alerts_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(transaction_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_alerts_risk_event
        FOREIGN KEY (risk_event_id)
        REFERENCES risk_events(risk_event_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_alerts_status
        CHECK (
            alert_status IN (
                'PENDING',
                'SENT',
                'RESOLVED',
                'FAILED'
            )
        ),

    CONSTRAINT chk_alerts_resolved_timestamp
        CHECK (
            resolved_at IS NULL
            OR sent_at IS NOT NULL
        )
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_transactions_account_id
    ON transactions(account_id);

CREATE INDEX idx_transactions_tx_date
    ON transactions(tx_date);

CREATE INDEX idx_transactions_account_date
    ON transactions(account_id, tx_date);

CREATE INDEX idx_risk_events_account_id
    ON risk_events(account_id);

CREATE INDEX idx_risk_events_transaction_id
    ON risk_events(transaction_id);

CREATE INDEX idx_alerts_account_id
    ON alerts(account_id);

CREATE INDEX idx_alerts_transaction_id
    ON alerts(transaction_id);

CREATE INDEX idx_alerts_risk_event_id
    ON alerts(risk_event_id);

COMMIT;
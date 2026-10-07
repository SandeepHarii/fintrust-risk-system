-- FinTrust Transaction Insights and Risk Monitoring System
-- Seed Data
-- 12 customers, 12 accounts, 240 transactions
-- Transaction period: July 2026 - September 2026

BEGIN;

-- ============================================================
-- CUSTOMERS
-- ============================================================

INSERT INTO customers (
    customer_id,
    customer_name
)
SELECT
    (
        '00000000-0000-0000-0000-' ||
        LPAD(customer_no::text, 12, '0')
    )::uuid,
    CASE customer_no
        WHEN 1 THEN 'Thabo Mokoena'
        WHEN 2 THEN 'Lerato Dlamini'
        WHEN 3 THEN 'Aisha Khan'
        WHEN 4 THEN 'Daniel Smith'
        WHEN 5 THEN 'Naledi Molefe'
        WHEN 6 THEN 'Jason Naidoo'
        WHEN 7 THEN 'Priya Patel'
        WHEN 8 THEN 'Michael Jacobs'
        WHEN 9 THEN 'Zanele Ndlovu'
        WHEN 10 THEN 'Ryan Williams'
        WHEN 11 THEN 'Fatima Ahmed'
        WHEN 12 THEN 'Sipho Khumalo'
    END
FROM generate_series(1, 12) AS customer_no;


-- ============================================================
-- ACCOUNTS
-- ============================================================

INSERT INTO accounts (
    account_id,
    customer_id,
    account_number,
    account_status
)
SELECT
    (
        '10000000-0000-0000-0000-' ||
        LPAD(account_no::text, 12, '0')
    )::uuid,
    (
        '00000000-0000-0000-0000-' ||
        LPAD(account_no::text, 12, '0')
    )::uuid,
    '4100' || LPAD(account_no::text, 12, '0'),
    CASE
        WHEN account_no IN (10, 12) THEN 'SUSPENDED'
        ELSE 'ACTIVE'
    END
FROM generate_series(1, 12) AS account_no;


-- ============================================================
-- TRANSACTIONS
-- ============================================================

-- 240 transactions:
-- 20 transactions per account.
--
-- The generated data deliberately includes:
--   * High-value transactions above R50,000
--   * Cross-border transactions
--   * Multiple HIGH-risk transactions
--   * Transactions distributed across three months
--
-- Account 1 receives a concentrated group of transactions
-- during July to provide meaningful velocity/risk data.

INSERT INTO transactions (
    transaction_id,
    account_id,
    tx_date,
    amount,
    currency,
    transaction_type,
    source_country,
    destination_country,
    risk_flag
)
SELECT
    (
        '20000000-0000-0000-0000-' ||
        LPAD(transaction_no::text, 12, '0')
    )::uuid,
    (
        '10000000-0000-0000-0000-' ||
        LPAD(account_no::text, 12, '0')
    )::uuid,
    CASE
        -- Account 1: concentrated transactions for velocity testing
        WHEN account_no = 1 AND transaction_no <= 12
            THEN TIMESTAMPTZ '2026-07-15 09:00:00+02'
                 + ((transaction_no - 1) * INTERVAL '5 minutes')
        ELSE
            TIMESTAMPTZ '2026-07-01 09:00:00+02'
            + ((transaction_no - 1) * INTERVAL '9 hours')
    END,
    CASE
        WHEN transaction_no % 29 = 0 THEN 85000.00
        WHEN transaction_no % 17 = 0 THEN 62500.00
        WHEN transaction_no % 11 = 0 THEN 51000.00
        WHEN transaction_no % 7 = 0 THEN 24500.00
        WHEN transaction_no % 5 = 0 THEN 12500.00
        ELSE 1500.00 + ((transaction_no * 137) % 8500)
    END,
    'ZAR',
    CASE transaction_no % 5
        WHEN 0 THEN 'PAYMENT'
        WHEN 1 THEN 'TRANSFER'
        WHEN 2 THEN 'PURCHASE'
        WHEN 3 THEN 'DEPOSIT'
        ELSE 'WITHDRAWAL'
    END,
    CASE
        WHEN transaction_no % 13 = 0 THEN 'ZA'
        WHEN transaction_no % 13 = 1 THEN 'GB'
        WHEN transaction_no % 13 = 2 THEN 'US'
        WHEN transaction_no % 13 = 3 THEN 'DE'
        WHEN transaction_no % 13 = 4 THEN 'AE'
        ELSE 'ZA'
    END,
    CASE
        WHEN transaction_no % 13 = 0 THEN 'GB'
        WHEN transaction_no % 13 = 1 THEN 'ZA'
        WHEN transaction_no % 13 = 2 THEN 'ZA'
        WHEN transaction_no % 13 = 3 THEN 'ZA'
        WHEN transaction_no % 13 = 4 THEN 'ZA'
        ELSE 'ZA'
    END,
    CASE
        WHEN
            (
                CASE
                    WHEN transaction_no % 29 = 0 THEN 85000.00
                    WHEN transaction_no % 17 = 0 THEN 62500.00
                    WHEN transaction_no % 11 = 0 THEN 51000.00
                    ELSE 1500.00 + ((transaction_no * 137) % 8500)
                END
            ) > 50000
            AND transaction_no % 13 IN (0, 1, 2, 3, 4)
        THEN 'HIGH'

        WHEN
            (
                CASE
                    WHEN transaction_no % 29 = 0 THEN 85000.00
                    WHEN transaction_no % 17 = 0 THEN 62500.00
                    WHEN transaction_no % 11 = 0 THEN 51000.00
                    ELSE 1500.00 + ((transaction_no * 137) % 8500)
                END
            ) > 50000
            OR transaction_no % 13 IN (0, 1, 2, 3, 4)
        THEN 'MEDIUM'

        ELSE 'LOW'
    END
FROM (
    SELECT
        transaction_no,
        ((transaction_no - 1) % 12) + 1 AS account_no
    FROM generate_series(1, 240) AS transaction_no
) AS generated_transactions;


-- ============================================================
-- TARGETED RISK SCENARIOS
-- ============================================================

-- Account 5:
-- Four HIGH-risk transactions within a 30-day window.
-- This creates the required rolling 30-day risk-report scenario.

UPDATE transactions
SET tx_date = CASE transaction_id
    WHEN '20000000-0000-0000-0000-000000000017'
        THEN TIMESTAMPTZ '2026-08-07 09:00:00+02'

    WHEN '20000000-0000-0000-0000-000000000029'
        THEN TIMESTAMPTZ '2026-08-11 21:00:00+02'

    WHEN '20000000-0000-0000-0000-000000000209'
        THEN TIMESTAMPTZ '2026-08-17 09:00:00+02'

    WHEN '20000000-0000-0000-0000-000000000221'
        THEN TIMESTAMPTZ '2026-08-21 21:00:00+02'

    ELSE tx_date
END
WHERE transaction_id IN (
    '20000000-0000-0000-0000-000000000017',
    '20000000-0000-0000-0000-000000000029',
    '20000000-0000-0000-0000-000000000209',
    '20000000-0000-0000-0000-000000000221'
);


-- Account 11:
-- Additional high-value transactions create a second
-- qualifying account for the rolling 30-day report.

UPDATE transactions
SET
    amount = CASE transaction_id
        WHEN '20000000-0000-0000-0000-000000000095'
            THEN 62500.00
        WHEN '20000000-0000-0000-0000-000000000155'
            THEN 51000.00
        ELSE amount
    END,
    risk_flag = CASE transaction_id
        WHEN '20000000-0000-0000-0000-000000000095'
            THEN 'HIGH'
        WHEN '20000000-0000-0000-0000-000000000155'
            THEN 'HIGH'
        ELSE risk_flag
    END
WHERE transaction_id IN (
    '20000000-0000-0000-0000-000000000095',
    '20000000-0000-0000-0000-000000000155'
);


-- ============================================================
-- RISK EVENTS
-- ============================================================

-- Create one risk event for every HIGH-risk transaction.
-- This keeps the seeded risk-event data consistent with
-- the transaction risk flags.

INSERT INTO risk_events (
    risk_event_id,
    account_id,
    transaction_id,
    reason,
    risk_level
)
SELECT
    (
        '30000000-0000-0000-0000-' ||
        LPAD(SUBSTRING(t.transaction_id::text FROM 29)::text, 12, '0')
    )::uuid,
    t.account_id,
    t.transaction_id,
    CASE
        WHEN t.amount > 50000
             AND t.source_country <> t.destination_country
            THEN 'HIGH_AMOUNT,CROSS_BORDER'

        WHEN t.amount > 50000
            THEN 'HIGH_AMOUNT'

        WHEN t.source_country <> t.destination_country
            THEN 'CROSS_BORDER'

        ELSE 'HIGH_RISK_TRANSACTION'
    END,
    'HIGH'
FROM transactions t
WHERE t.risk_flag = 'HIGH';


-- ============================================================
-- ALERTS
-- ============================================================

-- Create an alert for every seeded HIGH-risk transaction.

INSERT INTO alerts (
    alert_id,
    account_id,
    transaction_id,
    risk_event_id,
    alert_status,
    sent_at
)
SELECT
    (
        '40000000-0000-0000-0000-' ||
        LPAD(SUBSTRING(t.transaction_id::text FROM 29)::text, 12, '0')
    )::uuid,
    t.account_id,
    t.transaction_id,
    (
        '30000000-0000-0000-0000-' ||
        LPAD(SUBSTRING(t.transaction_id::text FROM 29)::text, 12, '0')
    )::uuid,
    CASE
        WHEN ROW_NUMBER() OVER (ORDER BY t.tx_date) % 3 = 0
            THEN 'RESOLVED'
        WHEN ROW_NUMBER() OVER (ORDER BY t.tx_date) % 2 = 0
            THEN 'SENT'
        ELSE 'PENDING'
    END,
    CASE
        WHEN ROW_NUMBER() OVER (ORDER BY t.tx_date) % 3 = 0
             OR ROW_NUMBER() OVER (ORDER BY t.tx_date) % 2 = 0
            THEN TIMESTAMPTZ '2026-09-30 15:00:00+02'
        ELSE NULL
    END
FROM transactions t
WHERE t.risk_flag = 'HIGH';

COMMIT;
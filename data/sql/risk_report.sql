-- FinTrust Transaction Insights and Risk Monitoring System
-- D4: SQL Analytics and Reporting Layer
-- CTE-based rolling 30-day high-risk account report
-- Includes PERCENT_RANK fraud/risk ranking

WITH high_risk_transactions AS (
    SELECT
        t.transaction_id,
        t.account_id,
        t.tx_date,
        t.amount,
        t.currency,
        t.transaction_type,
        t.source_country,
        t.destination_country
    FROM transactions t
    WHERE t.risk_flag = 'HIGH'
),

rolling_30_day_risk AS (
    SELECT
        h.account_id,
        h.tx_date AS window_end,
        COUNT(h2.transaction_id) AS high_risk_transactions_30d
    FROM high_risk_transactions h
    JOIN high_risk_transactions h2
        ON h2.account_id = h.account_id
        AND h2.tx_date BETWEEN h.tx_date - INTERVAL '30 days' AND h.tx_date
    GROUP BY
        h.account_id,
        h.tx_date
    HAVING COUNT(h2.transaction_id) > 3
),

account_risk_summary AS (
    SELECT
        account_id,
        MAX(high_risk_transactions_30d) AS max_high_risk_transactions_30d,
        COUNT(*) AS qualifying_windows
    FROM rolling_30_day_risk
    GROUP BY account_id
),

fraud_ranking AS (
    SELECT
        account_id,
        max_high_risk_transactions_30d,
        qualifying_windows,
        PERCENT_RANK() OVER (
            ORDER BY max_high_risk_transactions_30d
        ) AS fraud_percent_rank
    FROM account_risk_summary
)

SELECT
    f.account_id,
    a.account_number,
    a.account_status,
    f.max_high_risk_transactions_30d,
    f.qualifying_windows,
    ROUND((f.fraud_percent_rank * 100)::numeric, 2) AS fraud_percent_rank
FROM fraud_ranking f
JOIN accounts a
    ON a.account_id = f.account_id
ORDER BY
    f.max_high_risk_transactions_30d DESC,
    f.account_id;
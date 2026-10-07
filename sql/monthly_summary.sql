-- FinTrust Transaction Insights and Risk Monitoring System
-- D4: SQL Analytics and Reporting Layer
-- Monthly transaction summary with running account balance

SELECT
    t.account_id,
    a.account_number,
    DATE_TRUNC('month', t.tx_date)::date AS transaction_month,
    t.transaction_id,
    t.tx_date,
    t.amount,
    t.currency,
    t.transaction_type,
    t.risk_flag,

    SUM(t.amount) OVER (
        PARTITION BY t.account_id
        ORDER BY t.tx_date, t.transaction_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_balance

FROM transactions t
JOIN accounts a
    ON a.account_id = t.account_id

ORDER BY
    t.account_id,
    t.tx_date,
    t.transaction_id;
-- FinTrust Transaction Insights and Risk Monitoring System
-- D4: SQL Analytics and Reporting Layer
-- Compliance dashboard view

CREATE OR REPLACE VIEW compliance_dashboard AS
WITH transaction_summary AS (
    SELECT
        account_id,
        COUNT(*) AS total_transactions,
        COUNT(*) FILTER (WHERE risk_flag = 'HIGH') AS high_risk_transactions,
        COUNT(*) FILTER (WHERE risk_flag = 'MEDIUM') AS medium_risk_transactions,
        COUNT(*) FILTER (WHERE risk_flag = 'LOW') AS low_risk_transactions,
        MAX(tx_date) AS latest_transaction_date
    FROM transactions
    GROUP BY account_id
),

risk_summary AS (
    SELECT
        account_id,
        COUNT(*) AS risk_events
    FROM risk_events
    GROUP BY account_id
),

alert_summary AS (
    SELECT
        account_id,
        COUNT(*) AS alerts,
        COUNT(*) FILTER (WHERE alert_status = 'SENT') AS sent_alerts,
        COUNT(*) FILTER (WHERE alert_status = 'RESOLVED') AS resolved_alerts
    FROM alerts
    GROUP BY account_id
)

SELECT
    c.customer_id,
    c.customer_name,
    a.account_id,
    a.account_number,
    a.account_status,

    COALESCE(ts.total_transactions, 0) AS total_transactions,
    COALESCE(ts.high_risk_transactions, 0) AS high_risk_transactions,
    COALESCE(ts.medium_risk_transactions, 0) AS medium_risk_transactions,
    COALESCE(ts.low_risk_transactions, 0) AS low_risk_transactions,

    COALESCE(rs.risk_events, 0) AS risk_events,

    COALESCE(als.alerts, 0) AS alerts,
    COALESCE(als.sent_alerts, 0) AS sent_alerts,
    COALESCE(als.resolved_alerts, 0) AS resolved_alerts,

    ts.latest_transaction_date

FROM customers c
JOIN accounts a
    ON a.customer_id = c.customer_id

LEFT JOIN transaction_summary ts
    ON ts.account_id = a.account_id

LEFT JOIN risk_summary rs
    ON rs.account_id = a.account_id

LEFT JOIN alert_summary als
    ON als.account_id = a.account_id

ORDER BY
    a.account_number;
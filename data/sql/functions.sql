-- FinTrust Transaction Insights and Risk Monitoring System
-- D4: SQL Analytics and Reporting Layer
-- Stored function for atomically flagging an account

CREATE OR REPLACE FUNCTION flag_account(
    p_account_id UUID,
    p_reason VARCHAR(255)
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_risk_event_id UUID;
    v_transaction_id UUID;
BEGIN
    -- Find the most recent transaction for the account.
    SELECT transaction_id
    INTO v_transaction_id
    FROM transactions
    WHERE account_id = p_account_id
    ORDER BY tx_date DESC
    LIMIT 1;

    -- The account must have at least one transaction.
    IF v_transaction_id IS NULL THEN
        RAISE EXCEPTION 'Account % has no transaction to flag', p_account_id;
    END IF;

    -- Create the risk event.
    v_risk_event_id := gen_random_uuid();

    INSERT INTO risk_events (
        risk_event_id,
        account_id,
        transaction_id,
        reason,
        risk_level
    )
    VALUES (
        v_risk_event_id,
        p_account_id,
        v_transaction_id,
        p_reason,
        'HIGH'
    );

    -- Suspend the account.
    UPDATE accounts
    SET account_status = 'SUSPENDED'
    WHERE account_id = p_account_id;

    RETURN v_risk_event_id;
END;
$$;
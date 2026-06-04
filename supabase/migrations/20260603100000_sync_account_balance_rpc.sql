-- Create database function for atomic account balance sync
CREATE OR REPLACE FUNCTION public.sync_account_balance(p_account_id UUID, p_net_delta NUMERIC)
RETURNS NUMERIC AS $$
DECLARE
    v_new_balance NUMERIC;
BEGIN
    UPDATE public.accounts
    SET current_balance = COALESCE(current_balance, 0.0) + p_net_delta
    WHERE account_id = p_account_id
    RETURNING current_balance INTO v_new_balance;
    
    RETURN v_new_balance;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Migration to alter foreign key constraint on public.transactions to delete transactions when the parent account is deleted
ALTER TABLE public.transactions
  DROP CONSTRAINT IF EXISTS transactions_account_id_fkey,
  ADD CONSTRAINT transactions_account_id_fkey 
    FOREIGN KEY (account_id) 
    REFERENCES public.accounts(account_id) 
    ON DELETE CASCADE;

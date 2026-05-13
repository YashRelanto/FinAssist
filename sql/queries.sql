-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.accounts (
  account_id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  account_name text NOT NULL,
  account_type text NOT NULL CHECK (account_type = ANY (ARRAY['checking'::text, 'savings'::text, 'credit_card'::text, 'cash'::text, 'investment'::text, 'loan'::text, 'wallet'::text])),
  current_balance numeric NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT accounts_pkey PRIMARY KEY (account_id),
  CONSTRAINT accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id)
);
CREATE TABLE public.categories (
  category_id uuid NOT NULL DEFAULT gen_random_uuid(),
  main_category text NOT NULL CHECK (main_category = ANY (ARRAY['Food & Drinks'::text, 'Shopping'::text, 'Housing'::text, 'Transportation'::text, 'Vehicle'::text, 'Life & Entertainment'::text, 'Communication/PC'::text, 'Financial Expense'::text, 'Investments'::text, 'Income'::text, 'Others'::text])),
  sub_category text NOT NULL,
  CONSTRAINT categories_pkey PRIMARY KEY (category_id)
);
CREATE TABLE public.transactions (
  transaction_id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  account_id uuid,
  category_id uuid NOT NULL,
  transaction_date date NOT NULL,
  amount numeric NOT NULL,
  transaction_type text NOT NULL CHECK (transaction_type = ANY (ARRAY['income'::text, 'expense'::text, 'transfer'::text])),
  merchant_name text,
  description text,
  running_balance numeric,
  CONSTRAINT transactions_pkey PRIMARY KEY (transaction_id),
  CONSTRAINT transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id),
  CONSTRAINT transactions_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id),
  CONSTRAINT fk_transactions_category FOREIGN KEY (category_id) REFERENCES public.categories(category_id)
);
CREATE TABLE public.users (
  user_id uuid NOT NULL DEFAULT gen_random_uuid(),
  full_name text NOT NULL,
  email text NOT NULL UNIQUE,
  password text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  CONSTRAINT users_pkey PRIMARY KEY (user_id)
);
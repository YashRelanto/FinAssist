-- ============================================================
-- DROP EXISTING TABLES (in dependency order)
-- Run this before creating the new schema
-- ============================================================

drop table if exists public.transactions cascade;
drop table if exists public.accounts cascade;
drop table if exists public.categories cascade;
drop table if exists public.user_profiles cascade;
drop table if exists public.users cascade;

-- Optional: remove extension only if you are sure nothing else uses it
-- drop extension if exists pgcrypto;

-- ============================================================
-- PERSONAL FINANCE PLATFORM - CORE SCHEMA
-- ============================================================

create extension if not exists pgcrypto;

-- ============================================================
-- 1. USERS TABLE
-- ============================================================
create table public.users (
    user_id uuid primary key default gen_random_uuid(),

    full_name text not null,
    email text not null unique,

    created_at timestamptz not null default now(),
    deleted_at timestamptz
);

-- ============================================================
-- 1.5 USER PROFILES TABLE (Normalized Extensible Fields)
-- ============================================================
create table public.user_profiles (
    user_id uuid primary key references public.users(user_id) on delete cascade,
    onboarded boolean not null default false,
    income numeric(14,2) not null default 0,
    city_tier text not null default 'Metro',
    fixed_rent numeric(14,2) not null default 0,
    fixed_emi numeric(14,2) not null default 0,
    biggest_category text not null default '',
    primary_goal text not null default '',
    created_at timestamptz not null default now()
);

-- ============================================================
-- 2. CATEGORIES TABLE
-- ============================================================
create table public.categories (
    category_id uuid primary key default gen_random_uuid(),

    main_category text not null check (
        main_category in (
            'Food & Drinks',
            'Shopping',
            'Housing',
            'Transportation',
            'Vehicle',
            'Life & Entertainment',
            'Financial Expenses',
            'Investments',
            'Income'
        )
    ),

    sub_category text not null,

    unique (main_category, sub_category)
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
  CONSTRAINT transactions_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(account_id) ON DELETE CASCADE,
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
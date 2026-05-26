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
);

-- ============================================================
-- 3. ACCOUNTS TABLE
-- ============================================================
create table public.accounts (
    account_id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references public.users(user_id)
        on delete cascade,

    account_name text not null,

    account_type text not null check (
        account_type in (
            'checking',
            'savings',
            'credit_card',
            'cash',
            'investment',
            'loan',
            'wallet'
        )
    ),

    current_balance numeric(14,2) not null default 0,

    created_at timestamptz not null default now()
);

-- ============================================================
-- 4. TRANSACTIONS TABLE
-- ============================================================
create table public.transactions (
    transaction_id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references public.users(user_id)
        on delete cascade,

    account_id uuid
        references public.accounts(account_id)
        on delete set null,

    category_id uuid not null
        references public.categories(category_id)
        on delete restrict,

    transaction_date date not null,

    amount numeric(14,2) not null,

    transaction_type text not null check (
        transaction_type in (
            'income',
            'expense',
            'transfer'
        )
    ),

    merchant_name text,
    description text
);

-- ============================================================
-- INDEXES
-- ============================================================

create index idx_accounts_user_id
    on public.accounts(user_id);

create index idx_transactions_user_id
    on public.transactions(user_id);

create index idx_transactions_account_id
    on public.transactions(account_id);

create index idx_transactions_category_id
    on public.transactions(category_id);

create index idx_transactions_date
    on public.transactions(transaction_date);
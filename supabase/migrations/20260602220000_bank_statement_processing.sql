-- ============================================================
-- BANK STATEMENT PROCESSING PIPELINE - SCHEMAS & MODIFICATIONS
-- ============================================================

-- 1. Uploaded Statements Table (tracks file uploads & metadata)
CREATE TABLE IF NOT EXISTS public.uploaded_statements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    statement_hash TEXT NOT NULL UNIQUE, -- SHA256 file hash to prevent double uploads
    upload_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING'
);

-- 2. Merchant Master Table (V1 deterministic mappings)
CREATE TABLE IF NOT EXISTS public.merchant_master (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_name TEXT NOT NULL UNIQUE, -- Normalized key (e.g. 'AMAZON')
    normalized_name TEXT NOT NULL,      -- Clean presentation name (e.g. 'Amazon')
    category TEXT NOT NULL,             -- Primary category (e.g. 'Shopping')
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 3. User Category Overrides Table (V1 user customization)
CREATE TABLE IF NOT EXISTS public.user_category_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    merchant_name TEXT NOT NULL, -- Normalized or raw name
    override_category_id UUID NOT NULL REFERENCES public.categories(category_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    UNIQUE (user_id, merchant_name)
);

-- 4. Async Processing Jobs Table (real-time progress logs)
CREATE TABLE IF NOT EXISTS public.processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    statement_id UUID NOT NULL REFERENCES public.uploaded_statements(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING', -- PENDING, PROCESSING, COMPLETED, FAILED
    progress INTEGER NOT NULL DEFAULT 0,          -- 0 to 100
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5. Augment the existing accounts table with optional bank metadata
ALTER TABLE public.accounts 
    ADD COLUMN IF NOT EXISTS bank_name TEXT,
    ADD COLUMN IF NOT EXISTS account_holder TEXT,
    ADD COLUMN IF NOT EXISTS account_number TEXT,
    ADD COLUMN IF NOT EXISTS ifsc TEXT,
    ADD CONSTRAINT unique_user_account_number UNIQUE (user_id, account_number);

-- 6. Modify core transactions table for tracking & uniqueness
ALTER TABLE public.transactions 
    ADD COLUMN IF NOT EXISTS statement_id UUID REFERENCES public.uploaded_statements(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS transaction_hash TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS normalized_merchant TEXT;

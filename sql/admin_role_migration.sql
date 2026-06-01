-- Optional: add admin role to users table (run in Supabase SQL editor)
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user'
  CHECK (role IN ('user', 'admin'));

-- Grant admin to a specific account (replace email)
UPDATE public.users SET role = 'admin' WHERE email = 'your-admin@example.com';

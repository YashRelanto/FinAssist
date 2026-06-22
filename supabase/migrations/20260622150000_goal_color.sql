-- Persist the user-chosen theme color for a savings goal (UI accent class, e.g. bg-primary).
ALTER TABLE public.goals
  ADD COLUMN IF NOT EXISTS color text NOT NULL DEFAULT 'bg-primary';

COMMENT ON COLUMN public.goals.color IS
  'UI theme accent class for the goal card (bg-primary | bg-secondary | bg-tertiary | bg-error | bg-outline)';

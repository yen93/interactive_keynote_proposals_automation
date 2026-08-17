-- Audit/dedup log for the Interactive Keynote proposal automation.
-- Mirrors the shape of Uncharted Ice's proposal_demo_notes_email_logs table
-- (same Supabase project: aivitcomiywiysrfwqxt / "MAGTestProject"), with
-- client_org/event_date/logo_replaced added for operational visibility.

create table if not exists public.interactive_keynote_proposal_logs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  message_id text unique,
  is_processed boolean not null default false,
  status text,                 -- 'success' | 'needs_review' | 'error'
  error_message text,
  proposal_link text,
  processed_at timestamptz,
  client_org text,
  event_date text,
  logo_replaced boolean not null default false
);

comment on table public.interactive_keynote_proposal_logs is
  'Audit/dedup log for the Interactive Keynote (James Castrission) proposal automation.';

alter table public.interactive_keynote_proposal_logs enable row level security;

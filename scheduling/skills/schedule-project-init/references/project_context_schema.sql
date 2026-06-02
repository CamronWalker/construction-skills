-- Reference copy of the wnd_projects and wnd_project_log tables. Live schema
-- lives in the Power BI Sync Supabase project (anwdfilrfczluhudtbzw); applied
-- via Supabase apply_migration (NOT by running this file).
--
-- Purpose: persist project-context state (job number, SmartPM/Procore links,
-- and an append-only project log) in Supabase, replacing the per-project
-- project-context.html as the source of truth for the schedule-project-init
-- refactor.
--
-- Inserts/updates come ONLY through the Westland MCP connector, which uses the
-- Supabase service-role key. created_by_email is stamped server-side from the
-- Procore-verified OAuth identity (ctx.props.email) and cannot be forged by the
-- client.
--
-- RLS is enabled with no public policies. Service-role bypasses RLS; anon and
-- authenticated PostgREST clients see and write nothing.

-- One row per project, keyed by Westland job number (W####).
create table public.wnd_projects (
  id                           uuid primary key default gen_random_uuid(),
  job_number                   text not null unique,            -- the key (W####)
  spm_project_id               int references public.spm_projects(id),  -- nullable, opportunistic
  project_name                 text,
  -- SmartPM
  smartpm_url                  text,
  smartpm_trends_url           text,
  smartpm_changelog_url        text,
  smartpm_project_name         text,
  -- Procore
  procore_company_id           text default '11093',
  procore_project_id           text,
  procore_documents_folder_id  text,
  -- Provenance
  source                       text default 'manual',           -- 'init' | 'migrated' | 'manual'
  created_by_email             text,                            -- stamped server-side from OAuth
  created_at                   timestamptz not null default now(),
  updated_at                   timestamptz not null default now()
);

-- One row per log entry, append-only.
create table public.wnd_project_log (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references public.wnd_projects(id) on delete cascade,
  body             text not null,
  category         text not null default 'note',  -- 'eot' | 'scope_change' | 'schedule_published' | ...
  created_at       timestamptz not null default now(),  -- the date-time link
  created_by_email text
);

create index wnd_project_log_project_created_idx on public.wnd_project_log (project_id, created_at);

-- NOTE: the bug-report schema (wnd_bug_reports) carries no updated_at touch
-- trigger -- it only tracks created_at. wnd_projects has an updated_at column,
-- but rather than add a trigger here we follow that lean precedent and let the
-- connector's upsert tool set updated_at = now() on every write. No trigger is
-- defined.

alter table public.wnd_projects enable row level security;
alter table public.wnd_project_log enable row level security;

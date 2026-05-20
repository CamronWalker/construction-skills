-- Reference copy of the wnd_bug_reports table. Live schema lives in the
-- Power BI Sync Supabase project (anwdfilrfczluhudtbzw); applied as migration
-- create_wnd_bug_reports on 2026-05-19.
--
-- Inserts come ONLY from the westland-feedback MCP service (in the
-- westland-mcps Cloudflare Worker), which uses the Supabase service-role key.
-- user_email is stamped server-side from the Procore-verified ctx.props.email
-- and cannot be forged by the client.
--
-- RLS is enabled with no public policies. Service-role bypasses RLS; anon and
-- authenticated PostgREST clients see and write nothing.

create table public.wnd_bug_reports (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  -- Core
  title           text not null,
  severity        text not null check (severity in ('low','medium','high','critical')),
  skill_or_tool   text,
  what_went_wrong text not null,
  suggested_fix   text,
  -- Repro context
  repro_steps     text,
  expected_behavior text,
  actual_behavior text,
  conversation_summary text,
  -- Environment
  environment     jsonb,
  user_email      text not null,
  -- Triage
  status          text not null default 'new' check (status in ('new','triaged','in_progress','fixed','wont_fix','duplicate')),
  triage_notes    text,
  triaged_at      timestamptz,
  triaged_by      text
);

create index wnd_bug_reports_created_at_idx on public.wnd_bug_reports (created_at desc);
create index wnd_bug_reports_status_created_at_idx on public.wnd_bug_reports (status, created_at desc);
create index wnd_bug_reports_skill_or_tool_idx on public.wnd_bug_reports (skill_or_tool);
create index wnd_bug_reports_user_email_created_at_idx on public.wnd_bug_reports (user_email, created_at desc);

alter table public.wnd_bug_reports enable row level security;

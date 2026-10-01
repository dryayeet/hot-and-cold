-- =====================================================================
-- outreach-agent: initial schema
-- Source of truth: architecture/08-database-schema.md (approved 2026-10-01)
-- Postgres 17 on Supabase. Multi-user, RLS on every table.
-- Deferred by design (see doc section 10): candidate_facts/resume_claims,
-- embeddings vector column, LLM usage table, A/B tables, LangGraph checkpoint.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Extensions and schemas
-- ---------------------------------------------------------------------
create extension if not exists citext      with schema extensions;  -- case-insensitive emails/domains
create extension if not exists moddatetime with schema extensions;  -- updated_at maintenance
create extension if not exists vector      with schema extensions;  -- pgvector (column added by a later migration)

create schema if not exists private;  -- security definer helpers, materialized views (never API-exposed)
-- schema "langgraph" is reserved for a future checkpointer; not created here.

-- ---------------------------------------------------------------------
-- 1. Profiles (1:1 with auth.users) and user settings
-- ---------------------------------------------------------------------
create table public.profiles (
  user_id               uuid primary key references auth.users (id) on delete cascade,
  full_name             text not null,
  signature             jsonb not null default '{}',            -- {linkedin, github, phone}
  timezone              text not null default 'Asia/Kolkata',
  send_days             smallint[] not null default '{1,2,3,4,5}',  -- ISO weekdays, Mon-Fri
  send_time             time not null default '08:30',
  daily_send_cap        smallint not null default 10 check (daily_send_cap between 1 and 20),
  match_threshold       smallint not null default 6 check (match_threshold between 0 and 10),
  follow_up_after_days  smallint not null default 7,
  close_after_days      smallint not null default 14,
  max_follow_ups        smallint not null default 1 check (max_follow_ups between 0 and 3),
  auto_reply_recheck_days smallint not null default 5,
  settings              jsonb not null default '{}',
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

-- auto-create a profile row on signup (Supabase standard pattern)
create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (user_id, full_name)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'full_name', split_part(new.email, '@', 1))
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------
-- 2. Candidate inputs (Phase 1). FACTS.md stored as a plain document
--    (answer 5); atomization deferred, sketch in doc section 10.
-- ---------------------------------------------------------------------
create table public.candidate_documents (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users (id) on delete cascade,
  kind           text not null check (kind in ('base_resume_tex', 'projects_md', 'facts_md', 'other')),
  version        int  not null,
  content        text,
  content_sha256 text not null,
  is_active      boolean not null default true,
  attributes     jsonb not null default '{}',
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (user_id, kind, version)
);
create unique index candidate_documents_one_active
  on public.candidate_documents (user_id, kind) where is_active;

-- ---------------------------------------------------------------------
-- 3. Campaigns and agent runs
-- ---------------------------------------------------------------------
create table public.campaigns (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references auth.users (id) on delete cascade,
  name                 text,
  role_prompt          text not null,
  parsed_signals       jsonb,
  target_company_count smallint not null default 50,
  status               text not null default 'draft'
                       check (status in ('draft', 'active', 'paused', 'completed', 'archived')),
  settings             jsonb not null default '{}',
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

create table public.agent_runs (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users (id) on delete cascade,
  campaign_id         uuid references public.campaigns (id) on delete set null,
  graph_name          text not null,
  trigger             text check (trigger in ('manual', 'scheduled', 'event')),
  status              text not null default 'running'
                      check (status in ('running', 'waiting_hitl', 'succeeded', 'failed', 'cancelled')),
  langgraph_thread_id text,
  started_at          timestamptz,
  finished_at         timestamptz,
  stats               jsonb,
  error               jsonb,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 4. Company intelligence (per-user copies, answer 1)
-- ---------------------------------------------------------------------
create table public.companies (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users (id) on delete cascade,
  name               text not null,
  domain             extensions.citext,
  website_url        text,
  linkedin_url       text,
  careers_url        text,
  locations          text[],
  industry           text,
  headcount_range    text,
  latest_snapshot_id uuid,                                        -- FK added after company_snapshots exists
  attributes         jsonb not null default '{}',
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create unique index companies_user_domain
  on public.companies (user_id, domain) where domain is not null;

create table public.company_snapshots (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users (id) on delete cascade,
  company_id        uuid not null references public.companies (id) on delete cascade,
  captured_at       timestamptz not null default now(),
  run_id            uuid references public.agent_runs (id) on delete set null,
  funding_stage     text,
  funding_amount    numeric(16,2),
  funding_currency  char(3),
  funding_date      date,
  headcount         int,
  growth_signal     jsonb,          -- hiring velocity, YoY headcount
  sentiment_score   numeric(2,1) check (sentiment_score between 1 and 5),
  sentiment_detail  jsonb,
  leadership        jsonb,
  valuation         numeric(16,2),
  revenue           numeric(16,2),
  traffic           jsonb,
  sources           jsonb,          -- url_citation annotations for provenance
  created_at        timestamptz not null default now()
);

alter table public.companies
  add constraint companies_latest_snapshot_fk
  foreign key (latest_snapshot_id) references public.company_snapshots (id) on delete set null;

create table public.company_news (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users (id) on delete cascade,
  company_id   uuid not null references public.companies (id) on delete cascade,
  kind         text check (kind in ('funding', 'launch', 'layoff', 'hiring', 'leadership', 'scandal', 'other')),
  title        text not null,
  url          text,
  published_at timestamptz,
  summary      text,
  created_at   timestamptz not null default now(),
  unique (user_id, company_id, url)
);

create table public.job_postings (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users (id) on delete cascade,
  company_id     uuid not null references public.companies (id) on delete cascade,
  title          text not null,
  url            text not null,
  source         text,
  location       text,
  remote_type    text,
  seniority      text,
  employment_type text,
  description    text,
  parsed         jsonb,             -- skills, stack, responsibilities, required vs preferred
  posted_at      timestamptz,
  first_seen_at  timestamptz not null default now(),
  last_seen_at   timestamptz not null default now(),
  status         text not null default 'open' check (status in ('open', 'closed', 'unknown')),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (user_id, url)
);

-- ---------------------------------------------------------------------
-- 5. Opportunities (core grain: one user + company + role)
-- ---------------------------------------------------------------------
create table public.opportunities (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users (id) on delete cascade,
  campaign_id     uuid not null references public.campaigns (id) on delete cascade,
  company_id      uuid not null references public.companies (id) on delete cascade,
  job_posting_id  uuid references public.job_postings (id) on delete set null,
  role_title      text not null,
  relevance_score smallint check (relevance_score between 1 and 10),
  status          text not null default 'discovered'
                  check (status in (
                    'discovered', 'researched', 'scored', 'needs_review', 'qualified',
                    'disqualified', 'resume_ready', 'drafted', 'in_outreach',
                    'responded', 'interviewing', 'offer', 'closed')),
  closed_reason   text check (closed_reason in (
                    'no_response', 'rejected', 'not_hiring', 'bounced',
                    'user_skipped', 'offer_accepted', 'offer_declined', 'other')),
  priority        smallint,
  tags            text[] not null default '{}',
  notes           text,
  archived_at     timestamptz,
  attributes      jsonb not null default '{}',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  -- re-discovery in a later campaign never duplicates; it emits opportunity.rediscovered
  unique nulls not distinct (user_id, company_id, job_posting_id)
);

-- ---------------------------------------------------------------------
-- 6. Contacts and email verification (per user, PII)
-- ---------------------------------------------------------------------
create table public.contacts (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users (id) on delete cascade,
  company_id        uuid not null references public.companies (id) on delete cascade,
  full_name         text,
  first_name        text,
  last_name         text,
  title             text,
  role_type         text check (role_type in ('hiring_manager', 'hr', 'ta', 'recruiter', 'founder', 'other')),
  linkedin_url      text,
  linkedin_verified boolean not null default false,
  source            text check (source in ('llm_search', 'hunter', 'careers_page', 'manual', 'other')),
  source_detail     jsonb,
  attributes        jsonb not null default '{}',
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create table public.contact_emails (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users (id) on delete cascade,
  contact_id          uuid not null references public.contacts (id) on delete cascade,
  email               extensions.citext not null,
  is_primary          boolean not null default false,
  source              text,
  verification_status text not null default 'unverified'
                      check (verification_status in
                        ('unverified', 'valid', 'invalid', 'catch_all', 'risky', 'disposable', 'unknown')),
  last_verified_at    timestamptz,
  bounced_at          timestamptz,   -- ground truth fed back from Gmail bounces
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (user_id, email)
);

create table public.email_verifications (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users (id) on delete cascade,
  contact_email_id uuid not null references public.contact_emails (id) on delete cascade,
  method           text not null check (method in
                     ('syntax', 'dns_mx', 'smtp_ping', 'hunter', 'zerobounce', 'neverbounce', 'other')),
  result           text not null,
  raw_response     jsonb,
  cost             numeric(10,4),
  checked_at       timestamptz not null default now()
);

create table public.opportunity_contacts (
  user_id        uuid not null references auth.users (id) on delete cascade,
  opportunity_id uuid not null references public.opportunities (id) on delete cascade,
  contact_id     uuid not null references public.contacts (id) on delete cascade,
  role           text not null default 'primary' check (role in ('primary', 'cc', 'fallback_hr')),
  primary key (opportunity_id, contact_id)
);

-- ---------------------------------------------------------------------
-- 7. Matching (Stage 2). Components sum: the PDF says "1-10" but its own
--    rubric sums to 0-10, so CHECK allows 0.
-- ---------------------------------------------------------------------
create table public.match_assessments (
  id                      uuid primary key default gen_random_uuid(),
  user_id                 uuid not null references auth.users (id) on delete cascade,
  opportunity_id          uuid not null references public.opportunities (id) on delete cascade,
  run_id                  uuid references public.agent_runs (id) on delete set null,
  model                   text,
  scorer_version          text,
  tech_stack_score        smallint not null check (tech_stack_score between 0 and 3),
  seniority_score         smallint not null check (seniority_score between 0 and 2),
  project_relevance_score smallint not null check (project_relevance_score between 0 and 3),
  company_signal_score    smallint not null check (company_signal_score between 0 and 2),
  total_score             smallint generated always as
                            (tech_stack_score + seniority_score + project_relevance_score + company_signal_score) stored,
  threshold_used          smallint not null,
  passed_gate             boolean generated always as
                            ((tech_stack_score + seniority_score + project_relevance_score + company_signal_score)
                             >= threshold_used) stored,
  keyword_matches         text[] not null default '{}',
  keyword_gaps            text[] not null default '{}',
  reasoning               text,
  is_current              boolean not null default true,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);
create unique index match_assessments_one_current
  on public.match_assessments (opportunity_id) where is_current;

-- ---------------------------------------------------------------------
-- 8. Resume customization (Stage 3). FACTS stays a plain file (answer 5);
--    resume_claims/candidate_facts deferred, sketch in doc section 10.
-- ---------------------------------------------------------------------
create table public.resume_versions (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references auth.users (id) on delete cascade,
  opportunity_id        uuid not null references public.opportunities (id) on delete cascade,
  base_document_id      uuid references public.candidate_documents (id) on delete set null,
  base_variant          text,             -- Backend/SDE, AI/ML, Data, Research
  tex_source            text,
  pdf_path              text,             -- resumes/{user_id}/{opportunity_id}/<file>.pdf
  storage_backend       text not null default 'supabase_storage',
  compile_status        text not null default 'pending'
                        check (compile_status in ('pending', 'compiled', 'failed', 'overflow_flagged')),
  page_count            smallint,
  passed_page_gate      boolean,
  compile_log           text,
  customization_summary jsonb,
  gaps_reported         text[] not null default '{}',
  is_final              boolean not null default false,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create unique index resume_versions_one_final
  on public.resume_versions (opportunity_id) where is_final;

-- ---------------------------------------------------------------------
-- 9. Mail, threads, replies (Stages 4 and 6)
-- ---------------------------------------------------------------------
create table public.email_threads (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users (id) on delete cascade,
  opportunity_id  uuid not null references public.opportunities (id) on delete cascade,
  gmail_thread_id text,
  subject         text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create unique index email_threads_gmail
  on public.email_threads (gmail_thread_id) where gmail_thread_id is not null;

create table public.outreach_messages (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references auth.users (id) on delete cascade,
  opportunity_id       uuid not null references public.opportunities (id) on delete cascade,
  thread_id            uuid not null references public.email_threads (id) on delete cascade,
  contact_email_id     uuid not null references public.contact_emails (id) on delete cascade,
  kind                 text not null check (kind in ('initial', 'follow_up')),
  sequence_no          smallint not null check (sequence_no between 0 and 3),  -- 0 = initial
  subject              text,
  body_text            text,
  resume_version_id    uuid references public.resume_versions (id) on delete set null,
  attachment_filename  text,
  model                text,
  template_key         text,            -- A/B hook, null for now
  gmail_draft_id       text,
  gmail_message_id     text,
  status               text not null default 'drafting'
                       check (status in (
                         'drafting', 'awaiting_approval', 'approved', 'scheduled', 'sent',
                         'bounced', 'failed', 'cancelled', 'rejected')),
  drafted_at           timestamptz,
  approved_at          timestamptz,
  scheduled_for        timestamptz,
  sent_at              timestamptz,
  send_timezone        text,            -- timezone in force at send, for analytics
  follow_up_due_at     timestamptz,     -- sent_at + profiles.follow_up_after_days
  word_count           smallint,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (thread_id, sequence_no)
);
create unique index outreach_messages_gmail_draft
  on public.outreach_messages (gmail_draft_id) where gmail_draft_id is not null;
create unique index outreach_messages_gmail_message
  on public.outreach_messages (gmail_message_id) where gmail_message_id is not null;

create table public.inbound_messages (
  id                        uuid primary key default gen_random_uuid(),
  user_id                   uuid not null references auth.users (id) on delete cascade,
  thread_id                 uuid not null references public.email_threads (id) on delete cascade,
  opportunity_id            uuid not null references public.opportunities (id) on delete cascade,
  in_reply_to_message_id    uuid references public.outreach_messages (id) on delete set null,
  gmail_message_id          text not null unique,
  from_email                extensions.citext,
  from_name                 text,
  is_from_contacted_address boolean not null default true,  -- false = forward detection
  received_at               timestamptz not null,
  body_text                 text,                            -- full text, answer 4
  classification            text not null default 'unclassified'
                            check (classification in (
                              'unclassified', 'auto_reply', 'interview_request', 'forwarded',
                              'rejection', 'not_hiring', 'positive_other', 'other')),
  classification_method     text check (classification_method in ('rule', 'llm', 'manual')),
  classification_confidence numeric(3,2),
  model                     text,
  needs_manual_review       boolean not null default false,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 10. Scheduling: durable job queue (Day 7 / Day 14 / recheck timers)
-- ---------------------------------------------------------------------
create table public.scheduled_actions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users (id) on delete cascade,
  opportunity_id  uuid references public.opportunities (id) on delete cascade,
  action          text not null check (action in (
                    'send_message', 'check_follow_up', 'recheck_auto_reply',
                    'close_no_response', 'run_discovery', 'poll_inbox')),
  target_id       uuid,
  due_at          timestamptz not null,
  status          text not null default 'pending'
                  check (status in ('pending', 'running', 'done', 'failed', 'cancelled')),
  attempts        smallint not null default 0,
  locked_at       timestamptz,
  locked_by       text,
  last_error      text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 11. HITL reviews (every human gate in one table)
-- ---------------------------------------------------------------------
create table public.hitl_reviews (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users (id) on delete cascade,
  opportunity_id uuid references public.opportunities (id) on delete cascade,
  gate          text not null check (gate in (
                  'low_match', 'draft_approval', 'follow_up_approval',
                  'resume_overflow', 'response_classification')),
  subject_type  text not null,   -- match_assessment | outreach_message | resume_version | inbound_message
  subject_id    uuid not null,   -- polymorphic; integrity via per-type triggers later
  status        text not null default 'pending'
                check (status in ('pending', 'approved', 'rejected', 'edited')),
  run_id        uuid references public.agent_runs (id) on delete set null,
  interrupt_id  text,            -- LangGraph interrupt to resume
  requested_at  timestamptz not null default now(),
  decided_at    timestamptz,
  decision_note text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 12. Interview prep (Stage 7)
-- ---------------------------------------------------------------------
create table public.interview_prep_packs (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references auth.users (id) on delete cascade,
  opportunity_id         uuid not null unique references public.opportunities (id) on delete cascade,
  trigger_message_id     uuid references public.inbound_messages (id) on delete set null,
  status                 text default 'pending' check (status in ('pending', 'researching', 'ready', 'stale')),
  company_deep_dive_path text,     -- prep/{user_id}/{opportunity_id}/...
  role_deep_dive_path    text,
  fit_analysis           jsonb,
  interview_structure    jsonb,
  top_questions          jsonb,
  prep_plan_path         text,
  storage_backend        text not null default 'supabase_storage',
  sources                jsonb,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create table public.interviews (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users (id) on delete cascade,
  opportunity_id   uuid not null references public.opportunities (id) on delete cascade,
  round_no         smallint not null,
  round_name       text,
  format           text check (format in ('online', 'in_person', 'async', 'other')),
  scheduled_at     timestamptz,
  duration_minutes smallint,
  outcome          text not null default 'pending'
                   check (outcome in ('pending', 'passed', 'failed', 'cancelled', 'no_show')),
  notes            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (opportunity_id, round_no)
);

-- ---------------------------------------------------------------------
-- 13. Events (analytics backbone, append-only)
-- ---------------------------------------------------------------------
create table public.event_types (
  key            text primary key,
  description    text,
  payload_schema jsonb
);

create table public.events (
  id            bigint generated always as identity primary key,
  user_id       uuid not null,
  occurred_at   timestamptz not null default now(),
  event_type    text not null references public.event_types (key),
  entity_type   text,
  entity_id     uuid,
  opportunity_id uuid,           -- denormalized on purpose: funnel queries skip joins
  campaign_id   uuid,
  run_id        uuid,
  actor         text check (actor in ('agent', 'user', 'system')),
  payload       jsonb not null default '{}',
  schema_version smallint not null default 1
);

insert into public.event_types (key, description) values
  ('opportunity.created',        'New opportunity row'),
  ('opportunity.status_changed', 'Status transition {from, to}'),
  ('opportunity.rediscovered',   'Existing opportunity found again by a later campaign'),
  ('company.snapshot_captured',  'New company intelligence snapshot'),
  ('contact.found',              'Contact discovered'),
  ('email.verified',             'Email verification ran {method, result}'),
  ('email.bounced',              'Gmail reported a bounce'),
  ('match.scored',               'Match assessment recorded {total, passed_gate}'),
  ('hitl.requested',             'Human gate opened'),
  ('hitl.decided',               'Human gate decided {decision}'),
  ('resume.compiled',            'Resume compiled {pages, passed_gate}'),
  ('resume.gate_failed',         'One-page gate failed'),
  ('message.drafted',            'Outreach draft created'),
  ('message.approved',           'HITL approved a draft'),
  ('message.scheduled',          'Draft queued for a send slot'),
  ('message.sent',               'Draft sent {at, timezone}'),
  ('reply.received',             'Inbound message stored'),
  ('reply.classified',           'Inbound message classified {type, method}'),
  ('followup.queued',            'Follow-up nudge queued'),
  ('llm.call',                   'LLM usage {model, tokens, cost, stage}'),
  ('run.started',                'Agent run started'),
  ('run.finished',               'Agent run finished {status}')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------
-- 14. Embeddings (model deferred per answer 2: no vector column yet;
--     a later migration adds it with the chosen dimension)
-- ---------------------------------------------------------------------
create table public.embeddings (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users (id) on delete cascade,
  entity_type    text not null check (entity_type in ('candidate_fact', 'job_posting', 'company', 'resume_claim')),
  entity_id      uuid not null,
  model          text,
  content_sha256 text not null,
  created_at     timestamptz not null default now(),
  unique nulls not distinct (entity_type, entity_id, model)
);

-- =====================================================================
-- 15. Indexes
-- =====================================================================
create index candidate_documents_user_kind   on public.candidate_documents (user_id, kind);
create index campaigns_user                  on public.campaigns (user_id);
create index agent_runs_user                 on public.agent_runs (user_id);
create index agent_runs_campaign             on public.agent_runs (campaign_id);
create index agent_runs_status               on public.agent_runs (status) where status in ('running', 'waiting_hitl');

create index companies_user                  on public.companies (user_id);
create index company_snapshots_company       on public.company_snapshots (company_id, captured_at desc);
create index company_news_company            on public.company_news (company_id, published_at desc);
create index job_postings_company            on public.job_postings (company_id);

create index opportunities_user_campaign     on public.opportunities (user_id, campaign_id, status);
create index opportunities_company           on public.opportunities (company_id);
create index opportunities_job_posting       on public.opportunities (job_posting_id);
create index opportunities_tags_gin          on public.opportunities using gin (tags);

create index contacts_user                   on public.contacts (user_id);
create index contacts_company                on public.contacts (company_id);
create index contact_emails_user             on public.contact_emails (user_id);
create index contact_emails_contact          on public.contact_emails (contact_id);
create index email_verifications_email       on public.email_verifications (contact_email_id, checked_at desc);
create index email_verifications_user        on public.email_verifications (user_id);
create index opportunity_contacts_contact    on public.opportunity_contacts (contact_id);
create index opportunity_contacts_user       on public.opportunity_contacts (user_id);

create index match_assessments_opportunity   on public.match_assessments (opportunity_id, created_at desc);
create index match_assessments_user          on public.match_assessments (user_id);
create index match_assessments_gaps_gin      on public.match_assessments using gin (keyword_gaps);
create index match_assessments_matches_gin   on public.match_assessments using gin (keyword_matches);

create index resume_versions_opportunity     on public.resume_versions (opportunity_id);
create index resume_versions_user            on public.resume_versions (user_id);

create index email_threads_opportunity       on public.email_threads (opportunity_id);
create index outreach_messages_opportunity   on public.outreach_messages (opportunity_id);
create index outreach_messages_user_status   on public.outreach_messages (user_id, status);
create index outreach_messages_scheduled     on public.outreach_messages (scheduled_for) where status = 'scheduled';
create index outreach_messages_thread        on public.outreach_messages (thread_id);
create index outreach_messages_email         on public.outreach_messages (contact_email_id);
create index inbound_messages_thread         on public.inbound_messages (thread_id, received_at desc);
create index inbound_messages_opportunity    on public.inbound_messages (opportunity_id);
create index inbound_messages_reply_to       on public.inbound_messages (in_reply_to_message_id);
create index inbound_messages_manual_review  on public.inbound_messages (user_id) where needs_manual_review;

create index scheduled_actions_due           on public.scheduled_actions (due_at) where status = 'pending';
create index scheduled_actions_opportunity   on public.scheduled_actions (opportunity_id);
create index scheduled_actions_user          on public.scheduled_actions (user_id);

create index hitl_reviews_pending            on public.hitl_reviews (user_id) where status = 'pending';
create index hitl_reviews_opportunity        on public.hitl_reviews (opportunity_id);
create index hitl_reviews_subject            on public.hitl_reviews (subject_type, subject_id);

create index interview_prep_packs_user       on public.interview_prep_packs (user_id);
create index interviews_opportunity          on public.interviews (opportunity_id, round_no);
create index interviews_user                 on public.interviews (user_id);

create index events_user_time                on public.events (user_id, occurred_at desc);
create index events_type_time                on public.events (event_type, occurred_at);
create index events_opportunity              on public.events (opportunity_id);
create index events_entity                   on public.events (entity_type, entity_id);
create index embeddings_user                 on public.embeddings (user_id);
create index embeddings_entity               on public.embeddings (entity_type, entity_id);

-- =====================================================================
-- 16. updated_at triggers (extensions.moddatetime) on all mutable tables
-- =====================================================================
do $$
declare t text;
begin
  foreach t in array array[
    'profiles', 'candidate_documents', 'campaigns', 'agent_runs',
    'companies', 'job_postings', 'opportunities', 'contacts', 'contact_emails',
    'match_assessments', 'resume_versions', 'email_threads', 'outreach_messages',
    'inbound_messages', 'scheduled_actions', 'hitl_reviews',
    'interview_prep_packs', 'interviews'
  ] loop
    execute format(
      'create trigger set_updated_at before update on public.%I
       for each row execute function extensions.moddatetime(updated_at);', t);
  end loop;
end $$;

-- =====================================================================
-- 17. Row Level Security
-- Pattern per Supabase docs: enable RLS, revoke default grants, grant back
-- only what a dashboard needs, one policy per operation, (select auth.uid())
-- wrapped for caching, user_id indexed leading (done above).
-- Inserts and deletes go through the agent's service_role connection
-- (bypasses RLS); browser clients read, plus targeted updates.
-- =====================================================================
do $$
declare t text;
begin
  -- enable RLS everywhere; revoke Supabase's default grants; grant read back
  foreach t in array array[
    'profiles', 'candidate_documents', 'campaigns', 'agent_runs',
    'companies', 'company_snapshots', 'company_news', 'job_postings',
    'opportunities', 'contacts', 'contact_emails', 'email_verifications',
    'opportunity_contacts', 'match_assessments', 'resume_versions',
    'email_threads', 'outreach_messages', 'inbound_messages',
    'scheduled_actions', 'hitl_reviews', 'interview_prep_packs', 'interviews',
    'event_types', 'events', 'embeddings'
  ] loop
    execute format('alter table public.%I enable row level security;', t);
    execute format('revoke all on public.%I from anon, authenticated;', t);
    execute format('grant select on public.%I to authenticated;', t);
  end loop;

  -- per-user select policies. event_types is excluded here: it is a shared
  -- lookup with no user_id column, handled separately below.
  foreach t in array array[
    'profiles', 'candidate_documents', 'campaigns', 'agent_runs',
    'companies', 'company_snapshots', 'company_news', 'job_postings',
    'opportunities', 'contacts', 'contact_emails', 'email_verifications',
    'opportunity_contacts', 'match_assessments', 'resume_versions',
    'email_threads', 'outreach_messages', 'inbound_messages',
    'scheduled_actions', 'hitl_reviews', 'interview_prep_packs', 'interviews',
    'events', 'embeddings'
  ] loop
    execute format($f$
      create policy "authenticated reads own %1$s"
      on public.%1$I for select to authenticated
      using ((select auth.uid()) = user_id);$f$, t);
  end loop;

  -- dashboard-editable tables also get update grants + policies
  foreach t in array array[
    'profiles', 'campaigns', 'opportunities', 'contacts', 'contact_emails',
    'outreach_messages', 'inbound_messages', 'scheduled_actions',
    'hitl_reviews', 'interviews'
  ] loop
    execute format('grant update on public.%I to authenticated;', t);
    execute format($f$
      create policy "authenticated updates own %1$s"
      on public.%1$I for update to authenticated
      using ((select auth.uid()) = user_id)
      with check ((select auth.uid()) = user_id);$f$, t);
  end loop;

  -- shared lookup table: readable by all authenticated users
  execute $f$
    create policy "authenticated reads event types"
    on public.event_types for select to authenticated
    using (true);$f$;
end $$;

-- =====================================================================
-- 18. Storage: private buckets + per-user prefix policies (answer 3)
-- =====================================================================
insert into storage.buckets (id, name, public)
values ('resumes', 'resumes', false), ('prep', 'prep', false)
on conflict (id) do nothing;

create policy "authenticated reads own files"
  on storage.objects for select to authenticated
  using (
    bucket_id in ('resumes', 'prep')
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy "authenticated writes own files"
  on storage.objects for insert to authenticated
  with check (
    bucket_id in ('resumes', 'prep')
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

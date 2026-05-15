create extension if not exists pgcrypto;
create extension if not exists vector;

create type provider_type as enum ('gmail', 'microsoft_graph');
create type rule_status as enum ('provisional', 'confirmed', 'retired');
create type feedback_decision as enum ('accept', 'modify', 'reject');
create type urgency_band as enum ('low', 'normal', 'high', 'critical');
create type sender_taxonomy as enum ('internal', 'external_known', 'external_unknown');

create table if not exists personas (
  id uuid primary key default gen_random_uuid(),
  profile_id text not null unique,
  display_name text not null,
  tone text not null,
  filing_taxonomy text not null,
  response_constraints text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists accounts (
  id uuid primary key default gen_random_uuid(),
  persona_id uuid not null references personas(id) on delete restrict,
  provider provider_type not null,
  primary_email text not null,
  display_name text not null,
  org_type text not null,
  timezone text not null default 'America/Edmonton',
  scopes text[] not null default '{}',
  consent_logged_at timestamptz,
  sync_checkpoint text,
  last_history_id text,
  last_delta_link text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, primary_email)
);

create table if not exists threads (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  provider_thread_id text not null,
  participant_set text[] not null default '{}',
  duration_days numeric(10,3) not null default 0,
  last_activity timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, provider_thread_id)
);

create table if not exists emails (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  thread_id uuid not null references threads(id) on delete cascade,
  provider_message_id text not null,
  sender_email text not null,
  recipient_emails text[] not null default '{}',
  subject text not null,
  body_ciphertext text,
  body_hash text not null,
  message_timestamp timestamptz not null,
  labels text[] not null default '{}',
  classification jsonb not null default '{}'::jsonb,
  sender_taxonomy sender_taxonomy,
  urgency urgency_band,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, provider_message_id),
  unique (account_id, body_hash)
);

create table if not exists contacts (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  canonical_email text not null,
  display_name text,
  aliases text[] not null default '{}',
  influence_score numeric(8,6) not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, canonical_email)
);

create table if not exists contact_edges (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  source_contact_id uuid not null references contacts(id) on delete cascade,
  target_contact_id uuid not null references contacts(id) on delete cascade,
  co_thread_count int not null default 0,
  recency_weight numeric(8,6) not null default 0,
  updated_at timestamptz not null default now(),
  unique (account_id, source_contact_id, target_contact_id)
);

create table if not exists filing_rules (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  path text[] not null,
  match_criteria jsonb not null default '{}'::jsonb,
  status rule_status not null default 'provisional',
  confidence_score numeric(4,3) not null default 0.5,
  human_approved boolean not null default false,
  user_override boolean not null default false,
  created_by text not null default 'learning_agent',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (created_by = 'learning_agent'),
  check (confidence_score >= 0 and confidence_score <= 1)
);

create table if not exists feedback (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  target_type text not null,
  target_id text not null,
  decision feedback_decision not null,
  user_note text,
  context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists decision_embeddings (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  source_type text not null,
  source_id uuid not null,
  summary text not null,
  embedding vector(1536),
  created_at timestamptz not null default now()
);

create index if not exists idx_threads_account_last_activity on threads(account_id, last_activity desc);
create index if not exists idx_emails_account_timestamp on emails(account_id, message_timestamp desc);
create index if not exists idx_emails_classification on emails using gin (classification);
create index if not exists idx_contacts_account_influence on contacts(account_id, influence_score desc);
create index if not exists idx_filing_rules_account_status on filing_rules(account_id, status);
create index if not exists idx_feedback_account_created on feedback(account_id, created_at desc);

alter table personas enable row level security;
alter table accounts enable row level security;
alter table threads enable row level security;
alter table emails enable row level security;
alter table contacts enable row level security;
alter table contact_edges enable row level security;
alter table filing_rules enable row level security;
alter table feedback enable row level security;
alter table decision_embeddings enable row level security;

create policy "service_role_all_personas" on personas for all using (auth.role() = 'service_role');
create policy "service_role_all_accounts" on accounts for all using (auth.role() = 'service_role');
create policy "service_role_all_threads" on threads for all using (auth.role() = 'service_role');
create policy "service_role_all_emails" on emails for all using (auth.role() = 'service_role');
create policy "service_role_all_contacts" on contacts for all using (auth.role() = 'service_role');
create policy "service_role_all_contact_edges" on contact_edges for all using (auth.role() = 'service_role');
create policy "service_role_all_filing_rules" on filing_rules for all using (auth.role() = 'service_role');
create policy "service_role_all_feedback" on feedback for all using (auth.role() = 'service_role');
create policy "service_role_all_decision_embeddings" on decision_embeddings
  for all using (auth.role() = 'service_role');

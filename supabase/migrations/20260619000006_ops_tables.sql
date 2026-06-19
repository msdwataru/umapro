-- ============================================================
-- 6. 運用監査領域
-- ============================================================

create table job_runs (
  id bigint generated always as identity primary key,
  job_name varchar(100) not null,
  job_type varchar(50) not null,
  status varchar(20) not null default 'queued',
  started_at timestamptz,
  finished_at timestamptz,
  target_date date,
  records_processed integer,
  error_summary text,
  created_at timestamptz not null default now(),
  constraint chk_job_runs_type check (job_type in ('ingest', 'feature', 'train', 'predict')),
  constraint chk_job_runs_status check (status in ('queued', 'running', 'success', 'failed'))
);
create index idx_job_runs_type_status on job_runs (job_type, status);
create index idx_job_runs_target_date on job_runs (target_date);
create index idx_job_runs_started_at on job_runs (started_at desc);

create table recommendation_audits (
  id bigint generated always as identity primary key,
  race_id bigint not null references races (id),
  race_entry_id bigint references race_entries (id),
  model_version_id bigint not null references model_versions (id),
  feature_set_id bigint not null references feature_sets (id),
  prediction_generated_at timestamptz not null,
  published_at timestamptz,
  payload_json jsonb not null,
  created_at timestamptz not null default now()
);
create index idx_recommendation_audits_race on recommendation_audits (race_id, published_at);
create index idx_recommendation_audits_model on recommendation_audits (model_version_id);
create index idx_recommendation_audits_payload on recommendation_audits using gin (payload_json);

create table system_logs (
  id bigint generated always as identity primary key,
  job_run_id bigint references job_runs (id),
  level varchar(20) not null,
  event_type varchar(50) not null,
  message text not null,
  context_json jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  constraint chk_system_logs_level check (level in ('info', 'warn', 'error'))
);
create index idx_system_logs_job_run on system_logs (job_run_id);
create index idx_system_logs_level_at on system_logs (level, occurred_at desc);
create index idx_system_logs_event_type on system_logs (event_type);
create index idx_system_logs_context on system_logs using gin (context_json);

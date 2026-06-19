-- ============================================================
-- 3. 分析・予測領域
-- ============================================================

create table feature_sets (
  id bigint generated always as identity primary key,
  feature_set_name varchar(100) not null,
  version varchar(50) not null,
  description text,
  feature_schema_json jsonb,
  training_cutoff_rule text,
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_feature_sets unique (feature_set_name, version)
);
create index idx_feature_sets_active on feature_sets (is_active);

create table model_versions (
  id bigint generated always as identity primary key,
  model_name varchar(100) not null,
  version varchar(50) not null,
  model_type varchar(50) not null,
  feature_set_id bigint not null references feature_sets (id),
  training_period_start date,
  training_period_end date,
  metrics_json jsonb,
  artifact_path varchar(255),
  is_production boolean not null default false,
  deployed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_model_versions unique (model_name, version)
);
create index idx_model_versions_feature_set on model_versions (feature_set_id);
create index idx_model_versions_production on model_versions (is_production);

create table model_predictions (
  id bigint generated always as identity primary key,
  race_entry_id bigint not null references race_entries (id),
  model_version_id bigint not null references model_versions (id),
  feature_set_id bigint not null references feature_sets (id),
  prediction_target varchar(30) not null,
  predicted_value numeric(12,6) not null,
  implied_probability numeric(12,6),
  edge_value numeric(12,6),
  prediction_rank smallint,
  predicted_at timestamptz not null,
  source_odds_snapshot_at timestamptz,
  created_at timestamptz not null default now(),
  constraint uq_model_predictions unique (race_entry_id, model_version_id, prediction_target, predicted_at)
);
create index idx_model_predictions_model_at on model_predictions (model_version_id, predicted_at);
create index idx_model_predictions_entry_target on model_predictions (race_entry_id, prediction_target);
create index idx_model_predictions_target_rank on model_predictions (prediction_target, prediction_rank);

create table prediction_reasons (
  id bigint generated always as identity primary key,
  model_prediction_id bigint not null references model_predictions (id),
  reason_type varchar(30) not null,
  display_order smallint not null,
  title varchar(100) not null,
  body text not null,
  score numeric(12,6),
  created_at timestamptz not null default now(),
  constraint chk_prediction_reasons_type check (reason_type in ('strength', 'risk', 'feature'))
);
create index idx_prediction_reasons_prediction on prediction_reasons (model_prediction_id, display_order);
create index idx_prediction_reasons_type on prediction_reasons (reason_type);

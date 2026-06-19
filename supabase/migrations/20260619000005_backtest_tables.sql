-- ============================================================
-- 5. バックテスト領域
-- ============================================================

create table backtest_runs (
  id bigint generated always as identity primary key,
  user_id uuid not null references user_profiles (id) on delete cascade,
  run_name varchar(100),
  status varchar(20) not null default 'queued',
  parameters_json jsonb not null,
  started_at timestamptz,
  finished_at timestamptz,
  error_message text,
  created_at timestamptz not null default now(),
  constraint chk_backtest_runs_status check (status in ('queued', 'running', 'completed', 'failed'))
);
create index idx_backtest_runs_user_created on backtest_runs (user_id, created_at desc);
create index idx_backtest_runs_status on backtest_runs (status);
create index idx_backtest_runs_params on backtest_runs using gin (parameters_json);

create table backtest_results (
  id bigint generated always as identity primary key,
  backtest_run_id bigint not null references backtest_runs (id) on delete cascade,
  bet_type_id smallint not null references bet_types (id),
  race_count integer not null,
  bet_count integer not null,
  hit_count integer not null,
  stake_amount numeric(14,2) not null,
  payout_amount numeric(14,2) not null,
  roi numeric(12,6) not null,
  hit_rate numeric(12,6) not null,
  max_drawdown numeric(12,6),
  avg_odds numeric(12,6),
  created_at timestamptz not null default now()
);
create index idx_backtest_results_run on backtest_results (backtest_run_id);
create index idx_backtest_results_bet_type on backtest_results (bet_type_id);

create table backtest_bets (
  id bigint generated always as identity primary key,
  backtest_run_id bigint not null references backtest_runs (id) on delete cascade,
  race_id bigint not null references races (id),
  race_entry_id bigint references race_entries (id),
  bet_type_id smallint not null references bet_types (id),
  selection_key varchar(100) not null,
  stake_amount numeric(12,2) not null,
  payout_amount numeric(12,2) not null,
  is_hit boolean not null,
  prediction_value numeric(12,6),
  edge_value numeric(12,6),
  created_at timestamptz not null default now()
);
create index idx_backtest_bets_run on backtest_bets (backtest_run_id);
create index idx_backtest_bets_race on backtest_bets (race_id);
create index idx_backtest_bets_hit on backtest_bets (is_hit);

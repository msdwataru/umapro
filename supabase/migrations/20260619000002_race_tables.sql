-- ============================================================
-- 2. レース領域
-- ============================================================

create table races (
  id bigint generated always as identity primary key,
  external_race_code varchar(100) not null,
  race_date date not null,
  racecourse_id bigint not null references racecourses (id),
  race_number smallint,
  race_name varchar(200),
  grade varchar(20),
  class_name varchar(100),
  track_type varchar(20) not null,
  distance_m integer not null,
  turn_type varchar(20),
  weather varchar(20),
  going varchar(20),
  scheduled_start_at timestamptz,
  field_size smallint,
  status varchar(20) not null default 'scheduled',
  data_source varchar(50) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_races_code unique (external_race_code),
  constraint uq_races_date_course_num unique (race_date, racecourse_id, race_number),
  constraint chk_races_status check (status in ('scheduled', 'open', 'closed', 'result_fixed'))
);
create index idx_races_race_date on races (race_date);
create index idx_races_course_date on races (racecourse_id, race_date);
create index idx_races_track_distance on races (track_type, distance_m);
create index idx_races_status_start on races (status, scheduled_start_at);

create table race_entries (
  id bigint generated always as identity primary key,
  race_id bigint not null references races (id),
  horse_id bigint not null references horses (id),
  jockey_id bigint references jockeys (id),
  trainer_id bigint references trainers (id),
  bracket_number smallint,
  horse_number smallint not null,
  sex_age varchar(20),
  carried_weight numeric(5,1),
  declared_weight_kg integer,
  declared_weight_diff_kg integer,
  blinkers_flag boolean,
  scratch_flag boolean not null default false,
  morning_line_popularity smallint,
  latest_win_odds numeric(10,2),
  latest_place_odds_min numeric(10,2),
  latest_place_odds_max numeric(10,2),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_race_entries_race_horse unique (race_id, horse_id),
  constraint uq_race_entries_race_num unique (race_id, horse_number)
);
create index idx_race_entries_horse on race_entries (horse_id);
create index idx_race_entries_jockey on race_entries (jockey_id);
create index idx_race_entries_trainer on race_entries (trainer_id);
create index idx_race_entries_odds on race_entries (race_id, latest_win_odds);

create table odds_snapshots (
  id bigint generated always as identity primary key,
  race_entry_id bigint not null references race_entries (id),
  snapshot_at timestamptz not null,
  win_odds numeric(10,2),
  place_odds_min numeric(10,2),
  place_odds_max numeric(10,2),
  popularity smallint,
  source_status varchar(20),
  created_at timestamptz not null default now(),
  constraint uq_odds_snapshots unique (race_entry_id, snapshot_at),
  constraint chk_odds_source_status check (source_status in ('normal', 'delayed', 'estimated'))
);
create index idx_odds_snapshots_at on odds_snapshots (snapshot_at);
create index idx_odds_snapshots_entry_at on odds_snapshots (race_entry_id, snapshot_at desc);

create table race_results (
  id bigint generated always as identity primary key,
  race_id bigint not null references races (id),
  result_fixed_at timestamptz,
  winning_time varchar(20),
  pace_summary varchar(50),
  lap_text text,
  weather_final varchar(20),
  going_final varchar(20),
  steward_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_race_results_race unique (race_id)
);
create index idx_race_results_fixed_at on race_results (result_fixed_at);

create table entry_results (
  id bigint generated always as identity primary key,
  race_entry_id bigint not null references race_entries (id),
  finish_position smallint,
  dead_heat_flag boolean not null default false,
  finish_time varchar(20),
  margin_text varchar(50),
  passing_order_text varchar(50),
  last3f numeric(5,1),
  final_corner_position smallint,
  prize_money numeric(12,0),
  abnormal_result_code varchar(20),
  popularity_final smallint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_entry_results_entry unique (race_entry_id)
);
create index idx_entry_results_position on entry_results (finish_position);
create index idx_entry_results_popularity on entry_results (popularity_final);

create table payouts (
  id bigint generated always as identity primary key,
  race_id bigint not null references races (id),
  bet_type_id smallint not null references bet_types (id),
  combination_key varchar(100) not null,
  payout_amount integer not null,
  popularity smallint,
  created_at timestamptz not null default now(),
  constraint uq_payouts unique (race_id, bet_type_id, combination_key)
);
create index idx_payouts_race_bet on payouts (race_id, bet_type_id);

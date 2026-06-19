-- ============================================================
-- 1. マスタ領域
-- ============================================================

create table racecourses (
  id bigint generated always as identity primary key,
  external_racecourse_code varchar(20) not null,
  name varchar(100) not null,
  short_name varchar(20) not null,
  region varchar(50),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_racecourses_code unique (external_racecourse_code)
);
create index idx_racecourses_name on racecourses (name);

create table horses (
  id bigint generated always as identity primary key,
  external_horse_code varchar(30) not null,
  name varchar(120) not null,
  sex varchar(10),
  birth_date date,
  sire_name varchar(120),
  dam_name varchar(120),
  breeder_name varchar(120),
  owner_name varchar(120),
  retired_at date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_horses_code unique (external_horse_code)
);
create index idx_horses_name on horses (name);
create index idx_horses_birth_date on horses (birth_date);

create table jockeys (
  id bigint generated always as identity primary key,
  external_jockey_code varchar(30) not null,
  name varchar(120) not null,
  affiliation varchar(120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_jockeys_code unique (external_jockey_code)
);
create index idx_jockeys_name on jockeys (name);

create table trainers (
  id bigint generated always as identity primary key,
  external_trainer_code varchar(30) not null,
  name varchar(120) not null,
  affiliation varchar(120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_trainers_code unique (external_trainer_code)
);
create index idx_trainers_name on trainers (name);

create table bet_types (
  id smallint generated always as identity primary key,
  code varchar(20) not null,
  name varchar(50) not null,
  is_mvp_target boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_bet_types_code unique (code)
);

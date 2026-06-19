-- ============================================================
-- 4. 会員領域
-- user_profiles は auth.users と統合し、承認制アクセスモデルを採用
-- ============================================================

create table user_profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name varchar(120),
  role varchar(20) not null default 'user',
  -- status: pending → approved → (inactive / withdrawn)
  -- admin が 'approved' に変更するまで機能にアクセスできない
  status varchar(20) not null default 'pending',
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint chk_user_profiles_role check (role in ('user', 'admin')),
  constraint chk_user_profiles_status check (status in ('pending', 'approved', 'inactive', 'withdrawn'))
);
create index idx_user_profiles_role_status on user_profiles (role, status);

-- auth.users 登録時に user_profiles を自動生成するトリガー
create or replace function handle_new_user()
returns trigger as $$
begin
  insert into public.user_profiles (id, display_name)
  values (new.id, new.raw_user_meta_data ->> 'display_name');
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- last_login_at を更新するトリガー
create or replace function handle_user_login()
returns trigger as $$
begin
  update public.user_profiles
  set last_login_at = now(), updated_at = now()
  where id = new.id;
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_sign_in
  after update of last_sign_in_at on auth.users
  for each row execute function handle_user_login();

-- user_subscriptions: 将来の課金対応のために骨格のみ作成
create table user_subscriptions (
  id bigint generated always as identity primary key,
  user_id uuid not null references user_profiles (id) on delete cascade,
  plan_code varchar(50) not null default 'free',
  status varchar(20) not null default 'active',
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  provider_subscription_id varchar(100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_user_subscriptions_status check (status in ('active', 'canceled', 'past_due'))
);
create index idx_user_subscriptions_user_status on user_subscriptions (user_id, status);
create index idx_user_subscriptions_plan_status on user_subscriptions (plan_code, status);

create table saved_filters (
  id bigint generated always as identity primary key,
  user_id uuid not null references user_profiles (id) on delete cascade,
  filter_name varchar(100) not null,
  filter_type varchar(30) not null,
  filter_json jsonb not null,
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint chk_saved_filters_type check (filter_type in ('race_analysis', 'backtest'))
);
create index idx_saved_filters_user on saved_filters (user_id);
create index idx_saved_filters_user_type on saved_filters (user_id, filter_type);
create index idx_saved_filters_json on saved_filters using gin (filter_json);

create table favorites (
  id bigint generated always as identity primary key,
  user_id uuid not null references user_profiles (id) on delete cascade,
  favorite_type varchar(20) not null,
  race_id bigint references races (id),
  horse_id bigint references horses (id),
  created_at timestamptz not null default now(),
  constraint chk_favorites_type check (favorite_type in ('race', 'horse'))
);
create index idx_favorites_user_type on favorites (user_id, favorite_type);
create unique index uq_favorites_user_race on favorites (user_id, race_id) where race_id is not null;
create unique index uq_favorites_user_horse on favorites (user_id, horse_id) where horse_id is not null;

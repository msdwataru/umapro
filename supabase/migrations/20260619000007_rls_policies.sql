-- ============================================================
-- 7. RLS ポリシー（承認制アクセスモデル）
-- ============================================================

-- ヘルパー関数: 承認済みユーザーかどうかを判定
create or replace function is_approved()
returns boolean as $$
  select exists (
    select 1 from public.user_profiles
    where id = auth.uid()
      and status = 'approved'
      and deleted_at is null
  );
$$ language sql security definer stable;

-- ヘルパー関数: admin かどうかを判定
create or replace function is_admin()
returns boolean as $$
  select exists (
    select 1 from public.user_profiles
    where id = auth.uid()
      and role = 'admin'
      and deleted_at is null
  );
$$ language sql security definer stable;

-- ============================================================
-- マスタ・レース系: 承認済みユーザーはSELECT可、adminは全操作可
-- ============================================================

alter table racecourses enable row level security;
create policy "approved_select_racecourses" on racecourses for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_racecourses" on racecourses for all to authenticated using (is_admin());

alter table horses enable row level security;
create policy "approved_select_horses" on horses for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_horses" on horses for all to authenticated using (is_admin());

alter table jockeys enable row level security;
create policy "approved_select_jockeys" on jockeys for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_jockeys" on jockeys for all to authenticated using (is_admin());

alter table trainers enable row level security;
create policy "approved_select_trainers" on trainers for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_trainers" on trainers for all to authenticated using (is_admin());

alter table bet_types enable row level security;
create policy "approved_select_bet_types" on bet_types for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_bet_types" on bet_types for all to authenticated using (is_admin());

alter table races enable row level security;
create policy "approved_select_races" on races for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_races" on races for all to authenticated using (is_admin());

alter table race_entries enable row level security;
create policy "approved_select_race_entries" on race_entries for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_race_entries" on race_entries for all to authenticated using (is_admin());

alter table odds_snapshots enable row level security;
create policy "approved_select_odds_snapshots" on odds_snapshots for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_odds_snapshots" on odds_snapshots for all to authenticated using (is_admin());

alter table race_results enable row level security;
create policy "approved_select_race_results" on race_results for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_race_results" on race_results for all to authenticated using (is_admin());

alter table entry_results enable row level security;
create policy "approved_select_entry_results" on entry_results for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_entry_results" on entry_results for all to authenticated using (is_admin());

alter table payouts enable row level security;
create policy "approved_select_payouts" on payouts for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_payouts" on payouts for all to authenticated using (is_admin());

-- ============================================================
-- 分析・予測系
-- ============================================================

alter table feature_sets enable row level security;
create policy "approved_select_feature_sets" on feature_sets for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_feature_sets" on feature_sets for all to authenticated using (is_admin());

alter table model_versions enable row level security;
create policy "approved_select_model_versions" on model_versions for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_model_versions" on model_versions for all to authenticated using (is_admin());

alter table model_predictions enable row level security;
create policy "approved_select_model_predictions" on model_predictions for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_model_predictions" on model_predictions for all to authenticated using (is_admin());

alter table prediction_reasons enable row level security;
create policy "approved_select_prediction_reasons" on prediction_reasons for select to authenticated using (is_approved() or is_admin());
create policy "admin_all_prediction_reasons" on prediction_reasons for all to authenticated using (is_admin());

-- ============================================================
-- 会員系: 自分のデータのみ読み書き可
-- ============================================================

alter table user_profiles enable row level security;
-- 自分のプロフィールは参照・更新可
create policy "own_profile_select" on user_profiles for select to authenticated using (id = auth.uid());
create policy "own_profile_update" on user_profiles for update to authenticated using (id = auth.uid());
-- admin は全会員を参照・更新可
create policy "admin_all_user_profiles" on user_profiles for all to authenticated using (is_admin());

alter table user_subscriptions enable row level security;
create policy "own_subscriptions_select" on user_subscriptions for select to authenticated using (user_id = auth.uid());
create policy "admin_all_user_subscriptions" on user_subscriptions for all to authenticated using (is_admin());

alter table saved_filters enable row level security;
create policy "own_saved_filters" on saved_filters for all to authenticated
  using (user_id = auth.uid() and (is_approved() or is_admin()))
  with check (user_id = auth.uid() and (is_approved() or is_admin()));
create policy "admin_all_saved_filters" on saved_filters for all to authenticated using (is_admin());

alter table favorites enable row level security;
create policy "own_favorites" on favorites for all to authenticated
  using (user_id = auth.uid() and (is_approved() or is_admin()))
  with check (user_id = auth.uid() and (is_approved() or is_admin()));
create policy "admin_all_favorites" on favorites for all to authenticated using (is_admin());

-- ============================================================
-- バックテスト系: 承認済みユーザーは自分のデータのみ
-- ============================================================

alter table backtest_runs enable row level security;
create policy "own_backtest_runs" on backtest_runs for all to authenticated
  using (user_id = auth.uid() and (is_approved() or is_admin()))
  with check (user_id = auth.uid() and (is_approved() or is_admin()));
create policy "admin_all_backtest_runs" on backtest_runs for all to authenticated using (is_admin());

alter table backtest_results enable row level security;
create policy "own_backtest_results" on backtest_results for select to authenticated
  using (
    exists (select 1 from backtest_runs r where r.id = backtest_run_id and (r.user_id = auth.uid() or is_admin()))
  );
create policy "admin_all_backtest_results" on backtest_results for all to authenticated using (is_admin());

alter table backtest_bets enable row level security;
create policy "own_backtest_bets" on backtest_bets for select to authenticated
  using (
    exists (select 1 from backtest_runs r where r.id = backtest_run_id and (r.user_id = auth.uid() or is_admin()))
  );
create policy "admin_all_backtest_bets" on backtest_bets for all to authenticated using (is_admin());

-- ============================================================
-- 運用監査系: admin のみ
-- ============================================================

alter table job_runs enable row level security;
create policy "admin_all_job_runs" on job_runs for all to authenticated using (is_admin());

alter table recommendation_audits enable row level security;
create policy "admin_all_recommendation_audits" on recommendation_audits for all to authenticated using (is_admin());

alter table system_logs enable row level security;
create policy "admin_all_system_logs" on system_logs for all to authenticated using (is_admin());

-- ============================================================
-- 8. ロールへのGRANT（authenticatedとanonがテーブルにアクセスできるようにする）
-- ============================================================

-- authenticated ロール: 全テーブルへのSELECT（RLSポリシーで実際の制御を行う）
grant usage on schema public to authenticated, anon;

grant select, insert, update, delete on
  user_profiles,
  user_subscriptions,
  saved_filters,
  favorites
to authenticated;

grant select, insert, update, delete on
  backtest_runs,
  backtest_results,
  backtest_bets
to authenticated;

grant select, insert, update, delete on
  job_runs,
  recommendation_audits,
  system_logs
to authenticated;

grant select, insert, update, delete on
  racecourses,
  horses,
  jockeys,
  trainers,
  bet_types,
  races,
  race_entries,
  odds_snapshots,
  race_results,
  entry_results,
  payouts
to authenticated;

grant select, insert, update, delete on
  feature_sets,
  model_versions,
  model_predictions,
  prediction_reasons
to authenticated;

-- anon ロール: 最低限（ログインページ表示用）
grant select on racecourses, bet_types to anon;

-- sequence へのアクセス（insertに必要）
grant usage, select on all sequences in schema public to authenticated;

-- service_role: バッチ処理用（RLSをバイパスして全テーブルにアクセス）
grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;

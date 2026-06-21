# umapro — Claude 向けプロジェクト概要

競馬AI予測システム。レースデータを収集し、LightGBM Ranker で着順を予測して
Web UI で公開する承認制SaaS。

---

## リポジトリ構成

```
umapro/
├── apps/
│   ├── web/          # Next.js 16 フロントエンド（Supabase SSR）
│   └── batch/        # Python バッチ（データ取得・ML学習・予測生成）
│       ├── uma/
│       │   ├── ingest/       # データ取得（競馬ラボ・JRA）
│       │   ├── features/     # 特徴量生成
│       │   ├── models/       # モデル学習
│       │   ├── predictions/  # 予測生成・バックフィル
│       │   ├── backtest/     # バックテスト実行
│       │   ├── jobs/         # job_context（job_runs テーブルへの記録）
│       │   └── db/           # Supabase クライアント・paginate ユーティリティ
│       ├── artifacts/        # 生成済み parquet・モデルファイル
│       ├── tests/
│       └── .env              # ローカル Supabase 向け（本番は環境変数で上書き）
├── supabase/
│   └── migrations/   # テーブル定義 SQL（権威あるスキーマ情報源）
└── docs/
    ├── prediction_model_design.md  # 5フェーズ予測モデル設計
    └── feature_engineering_design.md
```

---

## DB 接続

**重要**: `apps/batch/.env` は `http://127.0.0.1:54321`（ローカル）向け。
本番バッチ実行時は必ず環境変数で上書きする。

```powershell
# PowerShell（本番接続）
$env:SUPABASE_URL="https://mfpglsftrfkwdguydlrg.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1mcGdsc2Z0cmZrd2RndXlkbHJnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTg2NzM0MiwiZXhwIjoyMDk3NDQzMzQyfQ.FHL_53rHvY2OIf8Oov6IJmo4poPlLeqyW4evsdAoHoY"
```

`service_role` キーは RLS をバイパスする。バッチ以外には使わない。

---

## 主要テーブル

| 領域 | テーブル | 概要 |
|------|----------|------|
| マスタ | `racecourses`, `horses`, `jockeys`, `trainers` | エンティティ情報 |
| レース | `races`, `race_entries`, `entry_results`, `payouts` | レース本体・出走・着順・払戻 |
| ML | `feature_sets`, `model_versions`, `model_predictions` | 特徴量定義・モデル管理・予測結果 |
| バックテスト | `backtest_runs`, `backtest_results`, `backtest_bets` | バックテスト実行記録 |
| 会員 | `user_profiles` | status: `pending` → `approved`（管理者が承認） |
| 運用 | `job_runs` | バッチ実行ログ。job_type: `ingest/feature/train/predict` |

**Supabase は 1 リクエスト 1000 行上限** → `uma.db.client.paginate()` を必ず使う。

---

## バッチ ML パイプライン

```
keibalab_job.py  ─→  races / race_entries / entry_results
        ↓
features/job.py  ─→  artifacts/race_features_v1.parquet
                       └ feature_sets テーブルに登録 (id=9, lgbm_ranker_v1)
        ↓
models/train_ranker.py  ─→  artifacts/lgbm_ranker_v1.txt
                              └ model_versions テーブルに登録 (id=10)
        ↓
predictions/backfill_job.py --model lgbm_ranker
                              └ model_predictions テーブルに書き込み
        ↓
backtest/job.py  ─→  backtest_results テーブル
```

### 現在のモデル状態（2026-06-20 時点）

| 項目 | 値 |
|------|-----|
| 学習データ | 2025-06-15 〜 2026-05-31（実質 2026 年分のみ） |
| 総レース数 | 1,674 レース / 23,221 出走結果 |
| 特徴量数 | 63 個（`jockey_affiliation_enc` は全件 -1 → 除外済み） |
| best_iteration | 12（データが浅いため早期収束） |
| 検証 ROI（6月） | **-41.9%**（アウトサンプル） |
| EV フィルタあり ROI | +493.6%（11 件のみ、参考値） |

---

## よく使うバッチコマンド

```bash
cd apps/batch

# 日次データ取得（競馬ラボ）
python -m uma.ingest.keibalab_job --date 20260620
python -m uma.ingest.keibalab_job --from 20260101 --to 20260620

# 特徴量生成
python -m uma.features.job --from-date 20260101 --to-date 20260620

# モデル学習（検証期間 = 6/1 以降）
python -m uma.models.train_ranker --val-from 20260601 --n-estimators 500

# 予測バックフィル
python -m uma.predictions.backfill_job --from-date 20260101 --to-date 20260620 --model lgbm_ranker
python -m uma.predictions.backfill_job --from-date 20260101 --to-date 20260620 --model rule_based

# バックテスト実行（run_id は backtest_runs を INSERT してから）
python -m uma.backtest.job --run-id <id>
python -m uma.backtest.job  # queued 全件処理
```

利用可能な prediction モデル: `rule_based` / `place_odds` / `odds_drift` / `course_form` / `lgbm_ranker`

---

## ユーザー管理

承認制アクセスモデル。`auth.users` にサインアップ → `user_profiles.status = 'pending'` で自動作成。管理者が `'approved'` に変更するまで機能にアクセス不可。

管理画面: `/admin/users`（role='admin' のユーザーのみアクセス可）

---

## 実装上の既知の注意点

| 項目 | 内容 |
|------|------|
| `_History.sort()` | `key=lambda x: x[0]` が必須。同日に複数出走した騎手等で dict 比較エラーになる |
| SC 正規化 | `std > 0` ではなく `(max-min) > 1e-9` で判定。浮動小数点ノイズで std ≈ 1.4e-17 になる場合がある |
| Python 丸め | `round(8.5) = 8`（銀行丸め）。`_dist_bucket(1700) = 1600`（1800 ではない） |
| `entry_results` | PostgREST は 1:1 関係でも配列で返すことがある → `er_raw[0] if isinstance(er_raw, list)` で処理 |
| `jockey_affiliation_enc` | 全件 -1（`jockeys.affiliation` が未投入）。特徴量から除外済み |

---

## フロントエンド構成

```
apps/web/src/app/
├── (marketing)/     # LP・ログイン・登録（認証不要）
├── (app)/           # ユーザー向け機能（approved ユーザーのみ）
│   ├── today/       # 今日のレース一覧
│   ├── races/       # レース検索・詳細・馬詳細
│   ├── picks/       # モデル推奨馬券
│   ├── analysis/    # 条件別成績分析
│   ├── backtest/    # バックテスト実行・結果
│   └── mypage/      # お気に入り・保存フィルタ
├── admin/           # 管理者専用（users / models / logs / sync）
└── pending/         # 承認待ち画面
```

# Phase0: 評価基盤の地固め（Foundation Hardening）

> 目的：Phase1〜4 で算出するすべての ROI 数字を「実運用で再現可能」かつ「統計的に信頼できる」状態にする。
> ここを固めずに先へ進むと、後段で得た優位性が **データリーク／過学習／オッズ取得タイミングのズレ** によって幻だったと最後に判明する。
> Phase0 完了前に Phase1 へ進んではならない。

---

## なぜ Phase0 が必要か（3つのサイレントキラー）

| # | 失敗モード | 症状 | 実運用での結末 |
|---|-----------|------|---------------|
| 1 | オッズの時間漏洩（Look-ahead） | バックテストROIが妙に良い | 確定オッズは締切後しか分からず、実運用で再現不能 |
| 2 | 時系列リーク | CVスコアが良いのに本番で崩れる | 未来情報で過去を予測してしまっている |
| 3 | 統計的有意性の欠如 | 「中穴でROI 110%」が出る | ベット数が少なく偶然。再現性ゼロ |

Phase0 はこの3つを **構造的に発生不能** にするための基盤を作る。

---

# Task 0-1: オッズ・タイムスナップショットの固定

## 原則
**「賭ける瞬間に観測可能な情報」だけで全特徴量・全オッズを構成する。**

確定オッズ（final odds）は **配当計算にのみ** 使用し、**購入判断には絶対に使わない**。

## 設計

### ベットタイムの定義
```text
BET_TIME = 発走 T-5分 (デフォルト)
```
- 理由：実運用で人間／APIが現実的に購入操作を完了できる最後のタイミング。
- 設定可能パラメータ化（T-1分 / T-5分 / T-15分）し、感度分析できるようにする。

### オッズの二層管理
```text
odds_at_bet    : BET_TIME 時点のオッズ（購入判断・特徴量に使う）
odds_final     : 確定オッズ（配当計算にのみ使う）
```

### バックテストの会計ルール（最重要）
```text
購入金額   = stake
購入可否   = odds_at_bet と P(win|BET_TIME) から計算した EV / Overlay で判定
払戻金額   = odds_final × stake   (的中時のみ)
利益       = 払戻金額 - stake
```
> 注意：日本の単勝はパリミュチュエル方式。`odds_at_bet` で買っても払戻は `odds_final` で決まる。
> 「odds_at_bet で買えると仮定し、odds_final で精算」が現実に最も近い保守的モデル。

### スナップショットが取れない場合の代替
過去データに時系列オッズが無い場合（確定オッズしか無い場合）：
- **暫定運用**：`odds_at_bet ≒ odds_final` と置くが、**結果に "OPTIMISTIC_BIAS" フラグを必ず付与**する。
- この場合の ROI は「実運用の上限値（楽観値）」として扱い、絶対に確定値として報告しない。
- 並行して時系列オッズの収集パイプラインを Phase0 のうちに着手する（最優先データ課題）。

## 成果物
- `snapshot_config.yaml` — BET_TIME 等の設定
- `odds_layer.parquet` — race_id × horse × {odds_at_bet, odds_final, snapshot_ts}
- `leakage_audit.md` — どの特徴量がどの時刻情報を使っているかの監査表

---

# Task 0-2: 特徴量リーク監査（Point-in-Time 保証）

## 目的
全特徴量について「BET_TIME 時点で確定しているか」を機械的に検証する。

## 監査表テンプレート（leakage_audit.md に出力）

| feature | データソース | 確定タイミング | BET_TIME時点で利用可? | 判定 |
|---------|------------|--------------|---------------------|------|
| latest_win_odds | オッズ | T-5分時点なら可 | ✅ | OK |
| popularity | オッズ由来 | 同上 | ✅ | OK |
| final_odds | オッズ | 締切後 | ❌ | **LEAK** |
| jockey_win_rate_365d | 過去成績 | 前日まで | ✅ | OK |
| course_form | 過去成績 | 前走まで | ✅ | OK |
| 上がり3F（当該レース） | レース結果 | レース後 | ❌ | **LEAK** |
| 馬体重 | 当日発表 | 発走前確定 | ✅ | OK（発表時刻を確認） |
| 馬場状態 | 当日 | 発走前確定 | ✅ | OK |

## 自動チェックの考え方
各特徴量に `available_at` タイムスタンプを付与し、`available_at <= BET_TIME` を満たさない行を学習・推論から除外。
```python
# 擬似コード
assert (features["available_at"] <= features["bet_time"]).all(), "Leakage detected"
```

## よくあるリーク（チェックリスト）
- [ ] 当該レースの着順・タイム・上がりを特徴量に入れていないか
- [ ] 「過去N走平均」の集計に当該レースが混入していないか（shift漏れ）
- [ ] 騎手/厩舎の勝率集計期間に未来のレースが入っていないか
- [ ] 確定オッズ・確定人気を特徴量に使っていないか
- [ ] 標準化（mean/std）を train+test 全体で計算していないか（→ train のみで fit）

---

# Task 0-3: 時系列分割（Walk-Forward）の標準化

## 原則
**ランダム分割は禁止。** 競馬は時系列であり、ランダム分割は未来→過去のリークを生む。

## 分割設計（Expanding Window 推奨）

```text
Fold 1:  Train [2018-2021]            -> Test [2022]
Fold 2:  Train [2018-2022]            -> Test [2023]
Fold 3:  Train [2018-2023]            -> Test [2024]
Fold 4:  Train [2018-2024]            -> Test [2025]
Fold 5:  Train [2018-2025]            -> Test [2026(現在まで)]
```

### Embargo（禁止帯）の挿入
Train と Test の境界に **数日〜数週間のギャップ** を入れ、集計特徴量（365日勝率など）が
Test 期間の情報を間接的に含むのを防ぐ。
```text
Train end: 2024-12-31
Embargo:   2025-01-01 〜 2025-01-14 (この期間は学習にも評価にも使わない)
Test start: 2025-01-15
```

### 最終評価のルール
- ハイパラ調整は **各 Fold の Train 内で完結**（Test を見てチューニングしない）。
- 報告する ROI は **全 Test Fold を連結した out-of-sample ROI**。
- 単一の train/test split の数字は信用しない。

## 成果物
- `cv_splits.json` — 各 Fold の期間定義（再現性のため固定）
- `walkforward_template.py` — 分割イテレータの共通実装

---

# Task 0-4: 市場ベースライン（天井と床）の確立

## 目的
モデルの良し悪しを「絶対値」でなく「市場に対する相対値」で測る基準線を引く。
**この基準を超えられないモデルに特徴量を足しても無駄。**

## 4つのベンチマーク

| ベースライン | 定義 | 意味 |
|------------|------|------|
| Random | 各レースで無作為に1頭購入 | 完全な床（控除率ぶん負ける ≒ -25%） |
| Favorite | 各レースで odds_at_bet 最低（1番人気）を購入 | 最も単純な戦略 |
| **Market（最重要）** | 市場確率 `1/odds_at_bet` を正規化したものを「予測」とみなした戦略 | **市場効率の天井**。これを超えて初めて「優位性あり」 |
| Model | course_form など自モデル | 評価対象 |

> Market ベースラインの含意：単勝は経験的にどの人気帯でも ROI 75〜85% に収束する（控除率の壁）。
> モデルが Market を **統計的有意に** 上回らない限り、それは「市場の写し」に過ぎない。

## 合格ライン（Phase1 への接続）
```text
必須:   Model ROI > Favorite ROI  かつ  Model > Market（有意差あり）
推奨:   Model > Market + 3pt
理想:   Model > Market + 5pt
```

## 成果物
- `baseline_comparison.csv`（Random / Favorite / Market / Model の ROI・的中率・ベット数・信頼区間）

---

# Task 0-5: 統計的有意性とリスクの計測基盤

## 目的
「ROI 110% が出た」が偶然か実力かを判定する仕組みを **全分析共通の関数** として用意する。

## 必須メトリクス（すべてのセル／帯に付与）

### 1. ベット数の最低閾値
```text
n_bets < 200 のセルは「参考値」扱い、太字・強調しない
n_bets < 50  は原則表示しない（ノイズ）
```

### 2. ROI の信頼区間（ブートストラップ）
レース単位（または日単位）で resample して ROI 分布を作る。
```python
# 擬似コード
def roi_ci(profits, stakes, n_boot=10000, block="race_id"):
    # ブロックブートストラップ（同一レース内の相関を保つ）
    # -> 95% CI [low, high] を返す
    ...
```
> **重要**：ベット単位の単純ブートストラップは不可。同一レース内のベットは相関するため、
> **レース単位のブロックブートストラップ** を使う。

### 3. ROI > 100% の片側検定
```text
H0: ROI <= 100%（市場に勝てていない）
ブートストラップ分布で P(ROI <= 100%) を算出
p < 0.05 で初めて「優位性あり」と主張可能
```

### 4. リスク指標（Phase3/4 のポートフォリオで再利用）
- Max Drawdown
- Sharpe / Sortino（日次損益ベース）
- 破産確率（Kelly 検証用）

## 成果物
- `metrics_lib.py` — `roi_ci()`, `roi_significance()`, `drawdown()` 等の共通関数
- `report_template.py` — 「ROI ± CI / n_bets / p値」を必ず併記する表生成ヘルパ

---

# Task 0-6: 再現性・実験管理の最小基盤

## 目的
「あのとき出た良いROI」を再現できる状態にする。属人化・上書き事故を防ぐ。

## 最小要件
- [ ] 乱数シード固定（学習・ブートストラップ・シミュレーション）
- [ ] データのバージョン（取得日・行数・ハッシュ）を成果物に刻む
- [ ] 各実験に `run_id` を付与し、設定（config）と結果（metrics）をペアで保存
- [ ] `snapshot_config.yaml` / `cv_splits.json` を git 管理し、結果と紐付け

## 成果物
- `experiment_log.csv`（run_id, date, config_hash, data_hash, OOS_ROI, CI, n_bets）

---

# Phase0 完了条件（Definition of Done）

すべて満たして初めて Phase1 へ進む。

- [ ] `odds_at_bet` と `odds_final` が分離され、会計ルールが実装済み
- [ ] 全特徴量のリーク監査表が作成され、LEAK 判定がゼロ
- [ ] Walk-Forward 分割（embargo付き）が共通実装として存在
- [ ] 4つのベースライン（特に Market）が ROI＋CI 付きで算出済み
- [ ] ブロックブートストラップによる ROI 信頼区間・有意性検定が共通関数化
- [ ] 乱数シード・データバージョンが固定され再現可能

---

# Phase0 成果物一覧

```text
snapshot_config.yaml         # ベットタイム等の設定
odds_layer.parquet           # odds_at_bet / odds_final の二層管理
leakage_audit.md             # 特徴量リーク監査表
cv_splits.json               # Walk-Forward 分割定義
walkforward_template.py      # 分割イテレータ
metrics_lib.py               # ROI CI・有意性・DD 等の共通関数
report_template.py           # CI/n_bets/p値併記の表生成
baseline_comparison.csv      # Random/Favorite/Market/Model
experiment_log.csv           # 実験トラッキング
phase0_report.md             # 上記の検証結果まとめ
```

---

# Phase0 → Phase1 の引き継ぎ判断

| 状態 | 判断 |
|------|------|
| Market ベースライン確立＆リーク・ゼロ | → Phase1（人気/オッズ/Calibration分析）へ。**全分析は metrics_lib の CI 付きで実施** |
| 時系列オッズが入手不能 | → OPTIMISTIC_BIAS フラグ運用＋オッズ収集パイプラインを並行着手。確定値としての ROI 報告は禁止 |
| リーク監査で LEAK 検出 | → 該当特徴量を除去・再集計してから Phase1。リークを残したまま進まない |

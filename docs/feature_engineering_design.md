# 競馬AI 特徴量設計ドキュメント

## 前提：現在のテーブル構造サマリ

```
races            → レース基本情報（コース・距離・馬場・グレード等）
race_entries     → 出走馬情報（斤量・馬体重・オッズ・枠番等）
entry_results    → 着順結果（走破タイム・上り3F・コーナー通過等）
race_results     → レース集計（pace_summary・lap_text）
horses           → 馬マスタ（血統・性別・生年月日等）
jockeys          → 騎手マスタ
trainers         → 調教師マスタ
odds_snapshots   → オッズ時系列スナップショット
```

---

## カラム別の取得可否

| カラム                        | テーブル           | 現在の値  | 備考                   |
| -------------------------- | -------------- | ----- | -------------------- |
| `finish_position`          | entry_results  | ✅ あり  | 学習ターゲット              |
| `finish_time`              | entry_results  | ✅ あり  | タイム予測ターゲット           |
| `last3f`                   | entry_results  | ✅ あり  | 上り3F（後半脚力指標）         |
| `latest_win_odds`          | race_entries   | ✅ あり  | 単勝オッズ                |
| `declared_weight_kg`       | race_entries   | ✅ あり  | 馬体重                  |
| `declared_weight_diff_kg`  | race_entries   | ✅ あり  | 馬体重変化                |
| `carried_weight`           | race_entries   | ✅ あり  | 斤量                   |
| `bracket_number`           | race_entries   | ✅ あり  | 枠番                   |
| `track_type`               | races          | ✅ あり  | 芝 / ダート / 障害         |
| `distance_m`               | races          | ✅ あり  | 距離                   |
| `weather`, `going`         | races          | ✅ あり  | 天候・馬場状態              |
| `field_size`               | races          | ✅ あり  | 出走頭数                 |
| `grade`                    | races          | ✅ あり  | GⅠ/GⅡ/GⅢ等           |
| `prize_money_1st`          | races          | ✅ あり  | 1着賞金（レースレベル指標）       |
| `sex`, `birth_date`        | horses         | ✅ あり  | 性別・年齢計算               |
| `sire_name`, `dam_name`    | horses         | ✅ あり  | 血統（one-hot or embedding） |
| `passing_order_text`       | entry_results  | ✅ あり  | コーナー通過順テキスト（要パース）    |
| `popularity_final`         | entry_results  | ✅ あり  | 最終人気（結果確定後）          |
| `affiliation`              | jockeys        | ✅ あり  | 美/栗/地/外               |
| `morning_line_popularity`  | race_entries   | ❌ NULL | スクレイパー未対応            |
| `latest_place_odds_min/max` | race_entries  | ❌ NULL | スクレイパー未対応            |
| `lap_text`                 | race_results   | ⚠️ テキスト | パース必要                |
| `pace_summary`             | race_results   | ⚠️ テキスト | ハイ/ミドル/スロー           |

---

## 特徴量カテゴリ一覧

### カテゴリ1: レース条件（静的）

| 特徴量名              | 元カラム                  | 変換                               |
| ----------------- | --------------------- | -------------------------------- |
| `track_type_enc`  | races.track_type      | 芝=0 / ダート=1 / 障害=2               |
| `distance_m`      | races.distance_m      | そのまま（数値）                         |
| `dist_bucket`     | races.distance_m      | `round(distance_m / 200) * 200`  |
| `field_size`      | races.field_size      | そのまま                             |
| `grade_enc`       | races.grade           | GⅠ=5 / GⅡ=4 / GⅢ=3 / OP=2 / その他=1 |
| `going_enc`       | races.going           | 良=0 / 稍重=1 / 重=2 / 不良=3         |
| `weather_enc`     | races.weather         | 晴=0 / 曇=1 / 雨=2 / 小雨=2          |
| `prize_money_1st` | races.prize_money_1st | log1p変換推奨                        |
| `race_number`     | races.race_number     | 1〜12                             |
| `weight_type_enc` | races.weight_type     | 馬齢=0 / 定量=1 / ハンデ=2 / 別定=3      |

---

### カテゴリ2: 当該出走エントリ（静的）

| 特徴量名                | 元カラム                               | 変換                   |
| ------------------- | ---------------------------------- | -------------------- |
| `bracket_number`    | race_entries.bracket_number        | 1〜8                  |
| `horse_number`      | race_entries.horse_number          | 1〜18                 |
| `carried_weight`    | race_entries.carried_weight        | 斤量(kg)               |
| `weight_kg`         | race_entries.declared_weight_kg    | 馬体重(kg)              |
| `weight_diff`       | race_entries.declared_weight_diff_kg | 前走比体重変化            |
| `latest_win_odds`   | race_entries.latest_win_odds       | 単勝オッズ                |
| `odds_inv`          | latest_win_odds                    | `1 / latest_win_odds` |
| `odds_rank`         | race_entries 内で集計                  | 人気順位（1=1番人気）        |
| `blinkers_flag`     | race_entries.blinkers_flag         | 0/1                  |
| `sex_enc`           | race_entries.sex_age               | 牡=0 / 牝=1 / 騸=2      |
| `age`               | race_entries.sex_age + races.race_date | 年齢（歳）              |

---

### カテゴリ3: 馬の過去成績（集計特徴量）

集計元: `entry_results` JOIN `race_entries` JOIN `races`

**全コース通算:**

| 特徴量名                      | 定義                              |
| ------------------------- | ------------------------------- |
| `horse_total_runs`        | 通算出走回数                          |
| `horse_win_rate`          | 通算勝率（1着 / 出走）                   |
| `horse_rentai_rate`       | 通算連対率（1〜2着 / 出走）                |
| `horse_fukusho_rate`      | 通算複勝率（1〜3着 / 出走）               |
| `horse_avg_finish`        | 通算平均着順                          |
| `horse_last_finish`       | 直近走の着順                          |
| `horse_last3_avg_finish`  | 直近3走の平均着順                       |
| `horse_last5_avg_finish`  | 直近5走の平均着順                       |
| `horse_finish_std`        | 直近5走の着順の標準偏差（安定度）              |
| `horse_avg_last3f`        | 直近5走の平均上り3F                     |
| `horse_last_last3f`       | 直近走の上り3F                        |

**コース×距離別（course_form）:**

| 特徴量名                       | 定義                                   |
| -------------------------- | ------------------------------------ |
| `horse_course_runs`        | 同コース×距離帯の出走回数                        |
| `horse_course_win_rate`    | 同コース×距離帯の勝率（サンプル<3なら0.5）            |
| `horse_course_fukusho_rate` | 同コース×距離帯の複勝率                        |
| `horse_dist_bucket_win_rate` | 同距離帯（コース問わず）の勝率                   |
| `horse_track_type_win_rate`  | 同馬場タイプ（芝/ダート）の勝率                  |

**時系列（前走情報）:**

| 特徴量名                 | 定義                          |
| -------------------- | --------------------------- |
| `days_since_last_run` | 前走からの間隔（日数）               |
| `distance_change`    | 前走比距離変化（m）                 |
| `prev_track_type`    | 前走の馬場（芝→ダートなどのコース変更）      |
| `prev_going`         | 前走の馬場状態                     |
| `prev_odds`          | 前走の単勝オッズ（市場評価の変化を見る）      |
| `prev_finish`        | 前走の着順                       |
| `prev_last3f`        | 前走の上り3F                     |
| `prev_corner_pos`    | 前走の最終コーナー位置（先行/差し等の脚質）    |

---

### カテゴリ4: 騎手の過去成績

| 特徴量名                          | 定義                         |
| ----------------------------- | -------------------------- |
| `jockey_total_runs`           | 通算騎乗数                      |
| `jockey_win_rate`             | 通算勝率                        |
| `jockey_rentai_rate`          | 通算連対率                       |
| `jockey_fukusho_rate`         | 通算複勝率                       |
| `jockey_course_win_rate`      | 同コース×距離帯での勝率               |
| `jockey_track_win_rate`       | 同馬場タイプでの勝率                  |
| `jockey_grade_win_rate`       | 重賞レースでの勝率（グレード別）           |
| `jockey_affiliation_enc`      | 美=0 / 栗=1 / 地=2 / 外=3      |

---

### カテゴリ5: 調教師の過去成績

| 特徴量名                          | 定義               |
| ----------------------------- | ---------------- |
| `trainer_win_rate`            | 通算勝率             |
| `trainer_course_win_rate`     | 同コース×距離帯での勝率     |
| `trainer_affiliation_enc`     | 美=0 / 栗=1 / 地=2  |

---

### カテゴリ6: レース内SC標準化（最重要）

> **同一レース内での相対偏差値化。** モデルが「このレースで相対的に強いか」を直接学習できる。

```python
# レース内でのz-score
def sc_normalize(series: pd.Series) -> pd.Series:
    mean = series.mean()
    std = series.std()
    if std == 0:
        return pd.Series([0.0] * len(series), index=series.index)
    return (series - mean) / std
```

| 特徴量名                        | 元特徴量                         |
| --------------------------- | ---------------------------- |
| `horse_avg_finish_sc`       | `horse_avg_finish`のレース内SC化  |
| `horse_win_rate_sc`         | `horse_win_rate`のレース内SC化    |
| `horse_course_win_rate_sc`  | `horse_course_win_rate`のSC化 |
| `jockey_win_rate_sc`        | `jockey_win_rate`のSC化       |
| `trainer_win_rate_sc`       | `trainer_win_rate`のSC化      |
| `carried_weight_sc`         | `carried_weight`のSC化（斤量の相対差）|
| `weight_diff_sc`            | `weight_diff`のSC化           |
| `age_sc`                    | `age`のSC化                   |

---

### カテゴリ7: 馬マスタ（血統・属性）

| 特徴量名          | 元カラム              | 変換                     |
| ------------- | ----------------- | ---------------------- |
| `sex_enc`     | horses.sex        | 牡=0 / 牝=1 / 騸=2        |
| `horse_age`   | horses.birth_date | race_dateから年齢計算         |
| `sire_name`   | horses.sire_name  | Label Encoding or 頻度エンコード |
| `dam_name`    | horses.dam_name   | Label Encoding           |

---

### カテゴリ8: 将来追加予定（現在NULL）

| 特徴量名                        | 必要カラム                          | 対応策                       |
| --------------------------- | ------------------------------ | ------------------------- |
| `morning_odds_drift`        | race_entries.morning_line_popularity | スクレイパー側で朝一オッズを取得する必要あり |
| `place_odds_mid`            | latest_place_odds_min/max      | 同上                        |
| `lap_split_early_pace`      | race_results.lap_text          | テキストパーサー実装（要工数）           |
| `pace_enc`                  | race_results.pace_summary      | ハイ/ミドル/スロー分類              |

---

## 全特徴量リスト（LightGBM投入用）

```python
FEATURE_COLUMNS = [
    # === レース条件 ===
    "track_type_enc",
    "distance_m",
    "dist_bucket",
    "field_size",
    "grade_enc",
    "going_enc",
    "weather_enc",
    "prize_money_1st_log",   # log1p(prize_money_1st)
    "race_number",
    "weight_type_enc",

    # === エントリ静的情報 ===
    "bracket_number",
    "horse_number",
    "carried_weight",
    "weight_kg",
    "weight_diff",
    "latest_win_odds",
    "odds_inv",              # 1 / latest_win_odds
    "odds_rank",             # 人気順位
    "blinkers_flag",
    "sex_enc",
    "age",

    # === 馬の通算成績 ===
    "horse_total_runs",
    "horse_win_rate",
    "horse_rentai_rate",
    "horse_fukusho_rate",
    "horse_avg_finish",
    "horse_last_finish",
    "horse_last3_avg_finish",
    "horse_last5_avg_finish",
    "horse_finish_std",
    "horse_avg_last3f",
    "horse_last_last3f",

    # === 馬のコース×距離適性 ===
    "horse_course_runs",
    "horse_course_win_rate",
    "horse_course_fukusho_rate",
    "horse_dist_bucket_win_rate",
    "horse_track_type_win_rate",

    # === 馬の前走情報 ===
    "days_since_last_run",
    "distance_change",
    "prev_track_type",
    "prev_going",
    "prev_finish",
    "prev_last3f",
    "prev_corner_pos",

    # === 騎手成績 ===
    "jockey_win_rate",
    "jockey_rentai_rate",
    "jockey_fukusho_rate",
    "jockey_course_win_rate",
    "jockey_track_win_rate",
    "jockey_affiliation_enc",

    # === 調教師成績 ===
    "trainer_win_rate",
    "trainer_course_win_rate",
    "trainer_affiliation_enc",

    # === SC標準化（レース内偏差値）===
    "horse_avg_finish_sc",
    "horse_win_rate_sc",
    "horse_course_win_rate_sc",
    "jockey_win_rate_sc",
    "trainer_win_rate_sc",
    "carried_weight_sc",
    "weight_diff_sc",
    "age_sc",

    # === 血統 ===
    "sire_enc",
    "dam_enc",
]
```

合計: **約60特徴量**

---

## 特徴量生成スクリプト設計

### ファイル構成

```
apps/batch/uma/features/
├── __init__.py
├── builder.py          ← メインのFeatureBuilder クラス
├── horse_stats.py      ← 馬の過去成績集計
├── jockey_stats.py     ← 騎手の過去成績集計
├── trainer_stats.py    ← 調教師の過去成績集計
├── course_form.py      ← コース×距離適性（既存ロジック移植）
├── normalize.py        ← SC標準化
└── encoders.py         ← カテゴリエンコーディング
```

### builder.py の骨格

```python
import pandas as pd
from uma.db.client import get_client, paginate

class FeatureBuilder:
    """
    指定日付範囲の全出走エントリから特徴量DataFrameを生成する。

    Usage:
        builder = FeatureBuilder()
        df = builder.build(start_date="2026-01-01", end_date="2026-06-14")
        df.to_parquet("race_features.parquet")
    """

    def __init__(self):
        self.client = get_client()

    def build(self, start_date: str, end_date: str) -> pd.DataFrame:
        # 1. ベーステーブル取得
        entries = self._fetch_entries(start_date, end_date)
        df = pd.DataFrame(entries)

        # 2. 静的エンコーディング
        df = self._encode_static(df)

        # 3. 過去成績集計（horse / jockey / trainer）
        horse_stats = self._build_horse_stats(df)
        jockey_stats = self._build_jockey_stats(df)
        trainer_stats = self._build_trainer_stats(df)

        df = df.merge(horse_stats, on=["race_entry_id", "horse_id"], how="left")
        df = df.merge(jockey_stats, on=["race_entry_id", "jockey_id"], how="left")
        df = df.merge(trainer_stats, on=["race_entry_id", "trainer_id"], how="left")

        # 4. SC標準化（レース内偏差値）
        df = self._sc_normalize(df)

        # 5. 欠損補完
        df = self._fill_missing(df)

        return df
```

### 学習ターゲット

```python
# 勾配爆発防止版（0〜1に正規化）
df["target"] = (df["field_size"] + 1 - df["finish_position"]) / df["field_size"]
```

---

## 実装優先順位

| 優先度 | 特徴量グループ         | 実装コスト | 期待効果 |
| --- | --------------- | ----- | ---- |
| 1   | レース条件（静的）       | 低     | 中    |
| 2   | エントリ静的情報 + オッズ  | 低     | 高    |
| 3   | 馬の通算成績（win_rate等）| 中     | 高    |
| 4   | コース×距離適性        | 低（既存） | 高    |
| 5   | SC標準化           | 中     | 非常に高い |
| 6   | 騎手・調教師成績        | 中     | 高    |
| 7   | 前走情報（時系列1ステップ）  | 中     | 高    |
| 8   | 血統エンコーディング      | 低     | 中    |
| 9   | ペース・ラップ情報       | 高（パース）| 高    |

---

## 注意事項

### データリークの防止

特徴量生成時、**集計対象は「その出走より前のレースのみ」** に限定する。

```python
# NG: 全期間で集計してしまう（未来データが混入）
horse_win_rate = results.groupby("horse_id")["is_win"].mean()

# OK: 各レースの race_date より前のデータのみ
def calc_horse_stats_at(horse_id, race_date, all_results):
    past = all_results[
        (all_results["horse_id"] == horse_id) &
        (all_results["race_date"] < race_date)
    ]
    return past["is_win"].mean()
```

### サンプル不足の扱い

```python
# 出走回数が少ない馬は中立値を使う
horse_win_rate = wins / runs if runs >= 3 else 0.5  # コース適性と同じ
```

### カテゴリ特徴量

LightGBMは欠損値・カテゴリ型を直接扱えるため、原則 `pd.Categorical` に変換。

```python
cat_cols = ["track_type_enc", "grade_enc", "going_enc", "sire_enc"]
for c in cat_cols:
    df[c] = df[c].astype("category")
```

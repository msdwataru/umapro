# 競馬AI 予測ロジック設計ドキュメント

## 概要

競馬AIの予測システムを段階的に構築するための設計方針。  
実戦ROI最大化の観点から、**ベイズ能力推定 → 特徴量生成 → LightGBM Ranker → 期待値計算 → 馬券選定** のパイプラインを基幹とする。

---

## モデル優先度マップ

| 優先度   | モデル                           | 用途           | 難易度 | 実戦性   |
| ----- | ----------------------------- | ------------ | --- | ----- |
| ★★★★★ | LightGBM Ranker (rank_xendcg) | レース内順位予測     | 低   | 非常に高い |
| ★★★★☆ | LightGBM Regression           | 走破タイム予測      | 低   | 高い    |
| ★★★★☆ | Bayesian Ability Model        | 馬・騎手能力値推定    | 中   | 高い    |
| ★★★☆☆ | LSTM                          | 成長曲線・時系列予測   | 中   | 中     |
| ★★☆☆☆ | Transformer Ranker            | レース内関係性の全体学習 | 高   | 非常に高い |

---

## 推奨アーキテクチャ（実戦パイプライン）

```text
ベイズ能力推定
  ↓ horse_strength / jockey_strength
特徴量生成（SC標準化含む）
  ↓ 100〜300特徴量
LightGBM Ranker
  ↓ prediction_rank / predicted_score
期待値計算
  EV = 推定勝率 × オッズ
  ↓
Chaos Filter
  chaos_score > 閾値 → スキップ
  ↓
馬券選定
```

> **Transformerから作るより、Bayesian Rating + SC標準化 + LightGBM Ranker + Chaos Filter の組み合わせの方が、少ないデータ量でも実運用レベルの精度に到達しやすい。**

---

## 開発フェーズ

| Phase | 実装内容                  | 出力                        |
| ----- | --------------------- | ------------------------- |
| 1     | LightGBM Ranker       | `prediction_rank`         |
| 2     | ベイズ能力推定               | `horse_sc`, `jockey_sc`   |
| 3     | Chaos Score モデル       | `chaos_score`             |
| 4     | 期待値計算・馬券フィルタ          | `edge_value`, 購入レース絞り込み   |
| 5     | Transformer Ranker 統合 | レース内全馬の関係性を考慮した最終スコアリング   |

---

## Phase 1: LightGBM Ranker

### 概要

資料において最も実績が高いとされるモデル。  
各レース内での相対的な順位を `rank_xendcg` 目的関数で学習する。

### 学習ターゲット（勾配爆発防止版）

$$target = \frac{field\_size + 1 - finish\_position}{field\_size}$$

**例: 18頭立て**

| 着順 | target |
| -- | ------ |
| 1着 | 1.000  |
| 2着 | 0.944  |
| 3着 | 0.889  |
| …  | …      |
| 18着 | 0.055  |

- ターゲット値を $[0, 1]$ に正規化することで、`Gain = 2^{rel} - 1` の指数爆発を防止する
- `metric='rmse'` を使用（`'ndcg'` は内部で整数キャストされ情報欠損の危険あり）

### 学習コード

```python
import lightgbm as lgb
import pandas as pd

df = pd.read_parquet("race_features.parquet")

target = (df["field_size"] + 1 - df["finish_position"]) / df["field_size"]

features = [
    "horse_sc",        # ベイズ能力値（SC標準化済み）
    "jockey_sc",       # 騎手能力値（SC標準化済み）
    "speed_index",     # スピード指数
    "distance_change", # 前走比距離変化
    "weight_change",   # 馬体重変化
    "odds",            # 単勝オッズ
    "draw",            # 枠番
]

X = df[features]
groups = df.groupby("race_id").size().values

ranker = lgb.LGBMRanker(
    objective="rank_xendcg",
    metric="rmse",
    learning_rate=0.03,
    num_leaves=63,
    n_estimators=1000,
)

ranker.fit(X, target, group=groups)
ranker.booster_.save_model("rank_model.txt")
```

### ポイント

- `group=` に各レースの頭数配列を渡すことでレース単位のランキング学習が成立する
- `rank_xendcg` は連続値ターゲットを受け付けるため、フロート型のスコアをそのまま最大化できる
- `lambdarank` は整数値のみのため競馬予測では `rank_xendcg` が事実上の標準

---

## Phase 2: ベイズ能力推定モデル

### 概要

「優秀な騎手が凡庸な馬を勝たせたのか」「名馬が騎手の技量を補ったのか」を分離して推定する。  
得られた `horse_strength` / `jockey_strength` をLightGBMの特徴量（SC化して）投入することで予測精度が大幅に向上する。

### Step 1: 簡易版（平均着順ベース）

```python
horse_rating = df.groupby("horse_id")["finish_position"].mean()
jockey_rating = df.groupby("jockey_id")["finish_position"].mean()
```

起点として使用。出走数が少ない馬・騎手は信頼区間が広いため後続のベイズ版で補正する。

### Step 2: Bradley-Terry モデル（実戦向け）

ペアワイズ比較から能力値を推定する。

```python
from choix import ilsr_pairwise

comparisons = []

for race_id, race_df in df.groupby("race_id"):
    sorted_df = race_df.sort_values("finish_position")
    horses = sorted_df["horse_id"].tolist()

    for i in range(len(horses)):
        for j in range(i + 1, len(horses)):
            comparisons.append((horses[i], horses[j]))

ratings = ilsr_pairwise(n_items=num_horses, data=comparisons)
```

出力: `horse_strength`（各馬の相対強さ）

### Step 3: 完全ベイズ版（Stan / PyMC）

馬と騎手の能力を同時分離する確率的モデル。

$$pf_h[g, i, r] \sim \text{Normal}(\mu_h[\text{HorseID}], \sigma_h[\text{HorseID}])$$
$$pf_j[g, i, r] \sim \text{Normal}(\mu_j[\text{JockeyID}], \sigma_j[\text{JockeyID}])$$
$$pf[g, i, r] = pf_h[g, i, r] + pf_j[g, i, r]$$

**事前分布:**

$$\mu_h[n] \sim \text{Normal}(0, \sigma_{\mu h}), \quad \sigma_h[n] \sim \text{Gamma}(10, 10)$$

**特徴量への変換（SC標準化）:**

推定された能力絶対値を「レース内での偏差値」に変換することで、相対的コンテキストがLightGBMに明示的に伝わる。

```text
[馬の絶対能力値] → (レース単位で平均・標準偏差算出) → [SC化（偏差値）]
                                                        ↓
                        [LightGBM] ← (レース内の「能力差」が鮮明化された状態で入力)
```

> SHAP分析では、SC化されたベイズ能力値（馬・騎手）が「人気度（単勝オッズ）」に次いで最重要特徴量として機能することが確認されている。

---

## Phase 3: Chaos Score モデル

### 概要

「このレースは予測できない」と判断し、投資をスキップするための分類器。  
予測精度ではなく **ドローダウンの回避** を目的とする。

### 入力特徴量（レースレベル）

```text
人気分散（オッズの分散）
能力分散（horse_strength の分散）
騎手能力分散
馬場状態（良・稍重・重・不良）
出走頭数
過去同コースの荒れ率
```

### 学習

```python
from lightgbm import LGBMClassifier

model = LGBMClassifier()

X = race_level_features
y = (race_actual_roi > 0).astype(int)  # そのレースで儲かったか

model.fit(X, y)
chaos_score = 1 - model.predict_proba(X_new)[:, 1]
```

### 投資フィルタ

```python
if chaos_score > 0.8:
    skip_bet = True
```

高カオスレース（不良馬場・混戦・大荒れ）を自動除外することで、突発的なドローダウンを回避する。

---

## Phase 4: 期待値計算・馬券選定

### 期待値（EV）の定義

$$EV = \hat{P}_{win} \times \text{odds} - 1$$

- $\hat{P}_{win}$: LightGBM Rankerが出力したスコアをsoftmax正規化した推定勝率
- $\text{odds}$: 単勝オッズ

### 購入条件

```python
if ev > 0 and chaos_score < threshold and prediction_rank == 1:
    place_bet = True
```

| 条件            | 意味                   |
| ------------- | -------------------- |
| `ev > 0`      | 期待値プラス（市場より有利な確率推定）  |
| `chaos_score < 0.8` | 荒れリスクが許容範囲内         |
| `prediction_rank == 1` | モデル最推薦馬              |

### Kelly基準（オプション）

資金管理に使用する。

$$f^* = \frac{EV}{\text{odds} - 1}$$

---

## Phase 5: Transformer Ranker（最終形態）

### 概要

レース内の全出走馬を「1つのシーケンス」として扱い、Self-Attentionで相互作用を学習する。  
計算コストが高いため、Phase 1〜4が安定してから導入する。

### アーキテクチャ

```python
import torch.nn as nn

class RaceTransformer(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model=128, nhead=8),
            num_layers=4,
        )
        self.head = nn.Linear(128, 1)

    def forward(self, x):
        # x: (batch, num_horses, feature_dim)
        x = self.encoder(x)
        return self.head(x).squeeze(-1)  # (batch, num_horses)
```

### LSTMとの比較

| 観点         | LSTM            | Transformer        |
| ---------- | --------------- | ------------------ |
| 時系列依存関係    | 逐次処理で保持         | Self-Attentionで全参照  |
| 計算コスト      | $O(L)$ 線形      | $O(L^2)$ 二乗       |
| 並列処理       | 困難              | 容易                 |
| テストMSE     | 中               | 低（長時系列で優位）         |
| 適用場面       | 馬の成長曲線（過去5走以上）  | レース内の全馬関係性         |

---

## LSTM: 馬の成長曲線モデル

### 目的

過去5走のシーケンスから「現在の調子・成長トレンド」を抽出する。  
LightGBM Rankerへの追加特徴量として利用する。

### 入力形式

```python
# 各馬の過去5走データ（系列長=5, 特徴量数=F）
x = [
    [speed1, weight1, odds1, ...],
    [speed2, weight2, odds2, ...],
    [speed3, weight3, odds3, ...],
    [speed4, weight4, odds4, ...],
    [speed5, weight5, odds5, ...],
]
```

### モデル

```python
import torch.nn as nn

class HorseLSTM(nn.Module):
    def __init__(self, input_size=32, hidden_size=128):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=2,
            batch_first=True,
        )
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        _, (h, _) = self.lstm(x)
        return self.fc(h[-1])
```

出力: `lstm_score`（隠れ状態ベクトルを1次元に圧縮した成長スコア）

---

## 特徴量設計（全フェーズ共通）

### カテゴリ別特徴量

| カテゴリ        | 特徴量例                                                |
| ----------- | --------------------------------------------------- |
| 馬能力系        | `horse_sc`, `horse_win_rate`, `lstm_score`          |
| 騎手能力系       | `jockey_sc`, `jockey_win_rate_by_course`            |
| オッズ系        | `odds`, `odds_rank`, `morning_line_drift`           |
| コース適性系      | `course_win_rate`, `dist_bucket_win_rate`           |
| 前走情報系       | `prev_finish`, `weight_change`, `distance_change`   |
| レース環境系      | `field_size`, `track_type`, `weather`, `turf_state` |
| SC標準化（レース内）  | `horse_sc_normalized`, `jockey_sc_normalized`       |

---

## データ要件

| データ項目         | 必須度 | 用途                       |
| ------------- | --- | ------------------------ |
| 出走データ（馬・騎手・オッズ） | 必須  | 全モデルの基礎入力                |
| 着順・走破タイム      | 必須  | 学習ターゲット                  |
| 馬体重・斤量        | 必須  | 特徴量                      |
| コース・距離・馬場状態   | 必須  | コース適性特徴量                 |
| 前走情報（過去5走以上）  | 推奨  | LSTM, コース適性モデル           |
| 血統情報          | 推奨  | コールドスタート補完（新馬戦）          |
| ラップタイム        | 任意  | スピード指数計算の精度向上            |

---

## 実装ロードマップ

```text
Week 1–2: Phase 1
  └── race_features.parquet の作成
  └── LightGBM Ranker 学習・バックテスト

Week 3–4: Phase 2
  └── Bradley-Terry モデル実装
  └── horse_sc / jockey_sc 特徴量追加
  └── SC標準化処理

Week 5–6: Phase 3
  └── Chaos Score モデル学習
  └── 投資フィルタ実装

Week 7: Phase 4
  └── EV計算 + Kelly基準
  └── /picks ページ統合

Week 8+: Phase 5
  └── LSTM / Transformer 実装・統合
```

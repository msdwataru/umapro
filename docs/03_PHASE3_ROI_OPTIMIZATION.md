# Phase3: ROI Optimization & Betting Strategy

## 統計的有意性の共通ルール（全Task適用）

Phase0 で共通実装した `metrics_lib.py` を使い、全集計表に以下を付与する。

* **n_bets < 200 のセルは「参考値」扱い**
* **n_bets < 50 のセルは非表示**
* **ROI信頼区間**：ブロックブートストラップ（race_id単位）95% CI
* **p値**：`H0: ROI <= 100%` の片側検定（p < 0.05 で有意）

---

## 目的

Phase1でモデルの優位性を検証し、

Phase2で市場との差分を抽出する特徴量を構築した。

しかし競馬で利益を出すためには

「最も勝つ馬」

を予測するだけでは不十分である。

重要なのは

「市場が過小評価している馬」

を発見することである。

Phase3では予測精度ではなくROI（回収率）の最大化を目的とする。

---

# 現状課題

現在のモデル

| 指標        | 値    |
| --------- | ---- |
| Hit Rate  | 高い   |
| ROI       | マイナス |
| EV Filter | 機能せず |

---

原因候補

* 予測確率のキャリブレーション不良
* オッズ依存
* 人気馬偏重
* EV計算精度不足
* ベット選択ロジック不足

---

# Phase3全体目標

現在

```text
ROI = -19.6%
```

↓

目標

```text
ROI = -10%
以内
```

↓

最終目標

```text
ROI = ±0%
付近
```

---

# Task1: Probability Calibration

## 目的

予測確率を実際の勝率へ近づける。

---

## 問題例

モデル

```text
勝率40%
```

予測

実際

```text
勝率28%
```

---

この状態ではEV計算が成立しない。

---

## 実装候補

### Platt Scaling

```python
CalibratedClassifierCV(method="sigmoid")
```

---

### Isotonic Regression

```python
CalibratedClassifierCV(method="isotonic")
```

---

### Beta Calibration

研究用途

---

### ⚠️ 必須：補正後のレース内正規化

Platt / Isotonic は各馬を**独立**に補正するため、補正後にレース内合計が 100% からズレる。
補正後は必ず **`race_id` 単位で softmax 再スケール** すること。

```python
# 補正後の正規化（必須）
df["prob_calibrated"] = df.groupby("race_id")["prob_raw"].transform(
    lambda x: x / x.sum()
)
```

これを省略すると EV 計算が再び壊れ、Task2 の Overlay も無効になる。

---

## 評価指標

* Brier Score
* LogLoss
* Calibration Error（ECE）
* **レース内合計の平均・最大偏差**（正規化後に 1.0 ± 0.001 以内であることを確認）

---

## 成果物

```text
calibrated_model.pkl
calibration_report.md
```

---

# Task2: EV Engine再設計

## 目的

真の期待値を計算する。

---

## 現行

```text
EV = P(win) × Odds
```

---

## 改良

### 市場補正

```text
Market Probability
=
1 / Odds
```

---

### Overlay

```text
Overlay
=
Model Probability
-
Market Probability
```

---

### Value Index

```text
Value Index
=
Model Probability
÷ Market Probability
```

---

## 出力

| Horse | Prob | Market | Overlay |
| ----- | ---- | ------ | ------- |
| A     |      |        |         |
| B     |      |        |         |

---

# Task3: Overlay Betting Strategy

## 目的

期待値のある馬のみ購入する。

---

## 条件例

### Conservative

```text
Overlay > 5%
```

---

### Standard

```text
Overlay > 10%
```

---

### Aggressive

```text
Overlay > 15%
```

---

## 比較

各戦略で

* ROI
* Hit Rate
* Bet数

を比較する。

---

# Task4: ROI学習モデル

## 目的

勝率ではなく利益を学習する。

---

## 現行

ターゲット

```text
1着=1
その他=0
```

---

## ⚠️ 素の `odds-1` ターゲットは採用禁止（分散爆発）

以下の案はレビューにより却下。

```text
profit = odds - 1  ← 禁止
```

理由：50倍で +49、外れで -1 という極端な歪み分布になる。
回帰が外れ値（高オッズ的中）に引きずられ機能しない。

---

## 代替案（優先順に列挙）

### 案A: log(odds) 重み付き分類（推奨）

```text
target = 1（的中） / 0（外れ）
sample_weight = log(odds)
```

高配当的中を重視しながら、分散爆発を防ぐ。

---

### 案B: ペアワイズ Profit Ranking

```text
同レース内でペアを作り
「A が B より高い利益をもたらすか」を二値分類
```

分布が安定し、ROI 直結で学習できる。

---

### 案C: クリップ付き Profit 回帰（最終手段）

```text
target = clip(odds - 1, max=20)
```

外れ値を抑制するが、高配当馬の情報を失う。

---

## 候補モデル

### LightGBM（案A/B）

---

### XGBoost（案B）

---

### CatBoost（案A）

---

## 評価

ROI基準（CI・p値付き）で評価。LogLoss 改善のみでは ROI 改善の証拠にならない。

---

# Task5: Bet Filter Optimization

## 目的

購入条件を探索する。

---

## パラメータ

### 最低勝率

```text
10%
15%
20%
25%
```

---

### Overlay

```text
5%
10%
15%
20%
```

---

### 最低オッズ

```text
2倍
3倍
5倍
```

---

### 最大オッズ

```text
20倍
30倍
50倍
```

---

## 実施

グリッドサーチ

---

## 出力

```text
bet_filter_grid.csv
```

---

# Task6: Kelly Criterion

## 目的

資金配分最適化

---

## 式

```text
f
=
(bp - q)
/
b
```

---

変数

```text
b = odds - 1
p = win probability
q = 1-p
```

---

## ⚠️ Kelly は「キャリブレーション完璧」が前提

確率が不正確だと過剰ベットで**即破産**する。
Kelly の適用は Phase3 Task1 の Calibration 完了（ECE < X%）後に限定する。

## 実装

### Quarter Kelly（既定・推奨）

25%

**既定値として採用**。確率推定に誤差がある実運用では Quarter Kelly 以下が安全。

---

### Half Kelly（条件付き）

50%

**条件**: ECE < 5% かつ Walk-Forward 全 Fold で ROI > Market が確認されてから解禁。

---

### Full Kelly

100%

理論上の最大成長だが、推定誤差があると破産リスクが極めて高い。**採用禁止**。

---

## 比較

* ROI
* Max Drawdown
* Profit

---

# Task7: Portfolio Simulation

## 目的

実運用時の資金推移確認

---

## 条件

初期資金

```text
100,000円
```

---

シミュレーション

* Fixed Bet
* Kelly
* Half Kelly

---

## 指標

### ROI

---

### Profit

---

### Max Drawdown

---

### Sharpe Ratio

---

### Recovery Factor

---

# Task8: Walk Forward Validation

## 目的

未来データでの再現性確認

---

## 方法

**Phase0 で定義した `cv_splits.json` と `walkforward_template.py` を使う。**
独自の train/test 分割は禁止。

### Expanding Window（Phase0定義準拠）

```text
Fold 1:  Train [2018-2021] → Test [2022]
Fold 2:  Train [2018-2022] → Test [2023]
Fold 3:  Train [2018-2023] → Test [2024]
Fold 4:  Train [2018-2024] → Test [2025]
Fold 5:  Train [2018-2025] → Test [2026(現在まで)]
```

各 Fold の境界には **Embargo（2週間）** を挿入する。

---

## 評価

* ROI（全 Test Fold 連結の out-of-sample ROI を報告）
* Hit Rate
* Profit
* **ROI 95% CI**（ブロックブートストラップ）
* **p値**（H0: ROI <= 100%、各 Fold および全体）

---

## NG（禁止）

* ランダム分割
* 単一 train/test split の数字のみ報告
* ハイパーパラメータを Test 期間を見てチューニング

---

# Task9: Strategy Leaderboard

## 目的

最終戦略比較

---

## 候補

### Course Form

---

### Ranker V2

---

### Overlay

---

### ROI Regressor

---

### Kelly

---

### Hybrid

---

## 出力

| Strategy | Bets | Hit | ROI |
| -------- | ---- | --- | --- |
|          |      |     |     |

---

# 成功基準

## 最低

```text
ROI > -15%
```

---

## 目標

```text
ROI > -10%
```

---

## 理想

```text
ROI > -5%
```

---

# 成果物

## モデル

* calibrated_model.pkl
* roi_regressor.pkl
* overlay_model.pkl

---

## 分析

* calibration_report.md
* overlay_analysis.csv
* kelly_simulation.csv
* strategy_leaderboard.csv

---

## レポート

* phase3_report.md

---

# Phase3完了条件

* キャリブレーション完了
* Overlay算出完了
* EV再設計完了
* ROI学習モデル作成
* Kellyシミュレーション完了
* Walk Forward検証完了
* 最良戦略決定

---

# Phase3終了時の判断

## ROI改善あり

ROIが市場平均を大きく上回る

↓

Phase4へ進む

---

## ROI改善なし

単勝市場での優位性不足

↓

馬券種拡張前にモデル再設計を検討する

* Pairwise Ranking
* Profit Ranking
* Reinforcement Learning
* Ensemble Learning

# Phase3: ROI Optimization & Betting Strategy

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

## 評価指標

* Brier Score
* LogLoss
* Calibration Error

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

## 新案

ターゲット

```text
profit
=
odds - 1
```

---

### 例

1.5倍

```text
0.5
```

---

10倍

```text
9
```

---

50倍

```text
49
```

---

## 候補モデル

### LightGBM Regressor

利益予測

---

### XGBoost Regressor

利益予測

---

### CatBoost Regressor

利益予測

---

## 評価

ROI基準で評価

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

## 実装

### Full Kelly

100%

---

### Half Kelly

50%

推奨

---

### Quarter Kelly

25%

安全型

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

### Train

2020-2024

### Test

2025

---

### Train

2020-2025

### Test

2026

---

## 評価

* ROI
* Hit Rate
* Profit

---

## NG

ランダム分割

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

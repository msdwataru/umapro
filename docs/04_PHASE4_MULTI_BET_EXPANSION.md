# Phase4: Multi-Bet Expansion & Portfolio Optimization

## 目的

Phase1〜Phase3で

* モデルの優位性検証
* 特徴量改善
* ROI最適化

を実施した。

Phase4では単勝モデルを基盤として

* ワイド
* 馬連
* 馬単
* 三連複
* 三連単

へ展開し、投資対象を拡張する。

---

# 前提条件

Phase3終了時点で

最低条件

```text
単勝ROI > -10%
```

推奨条件

```text
単勝ROI > -5%
```

理想

```text
単勝ROI >= 0%
```

単勝で優位性が確認できない場合は
Phase4へ進まない。

---

# 全体戦略

単勝モデル

↓

確率モデル

↓

着順分布モデル

↓

馬券期待値モデル

↓

ポートフォリオ最適化

---

# Task1: Top3 Probability Model

## 目的

1着だけでなく

* 2着
* 3着

の確率も推定する。

---

## 現状

```text
P(Win)
```

のみ

---

## 拡張

```text
P(1st)
P(2nd)
P(3rd)
```

---

## 候補

### Multiclass Model

着順分類

---

### Ranker

順位予測

---

### Plackett-Luce Model

推奨

---

## 出力

```text
finish_distribution.parquet
```

---

# Task2: ワイド予測エンジン

## 目的

最も現実的な利益源を構築する。

---

## 理由

ワイドは

* 的中率が高い
* 分散が低い
* 学習しやすい

---

## 条件

馬A

3着以内確率

```text
45%
```

馬B

3着以内確率

```text
35%
```

---

## 推定

```text
P(A and B in Top3)
```

---

## 出力

| Pair | Prob | Odds | EV |
| ---- | ---- | ---- | -- |

---

# Task3: 馬連予測エンジン

## 目的

連対ペアを予測する。

---

## 推定

```text
P(A-B Top2)
```

---

## 方法

### Monte Carlo

推奨

---

### Plackett-Luce

推奨

---

### Pairwise Model

補助

---

## 出力

```text
exacta_pairs.parquet
```

---

# Task4: 三連複予測エンジン

## 目的

ROI向上を狙う。

---

## 推定

```text
Top3 Combination
```

---

## 例

```text
1-4-9
```

---

## 手法

### Race Simulation

10000回

---

## 出力

| Combo | Prob |
| ----- | ---- |

---

# Task5: Monte Carlo Race Simulator

## 目的

全馬券種の基盤を作る。

---

## 方法

各馬

```text
Win Probability
```

から

レースをシミュレーション

---

## 回数

```text
10000
```

〜

```text
100000
```

回

---

## 出力

```text
race_simulation.parquet
```

---

## 活用

* 単勝
* ワイド
* 馬連
* 馬単
* 三連複
* 三連単

すべて利用可能

---

# Task6: Expected Value Engine V2

## 目的

馬券単位の期待値計算

---

## 計算

```text
EV
=
Probability × Odds
```

---

## 出力

| Ticket | Prob | Odds | EV |
| ------ | ---- | ---- | -- |

---

## フィルタ

### Conservative

```text
EV > 1.05
```

---

### Standard

```text
EV > 1.10
```

---

### Aggressive

```text
EV > 1.20
```

---

# Task7: Ticket Ranking System

## 目的

全馬券をランキング化する。

---

## Score

```text
score
=
EV
×
confidence
×
liquidity
```

---

## 出力

| Rank | Ticket | Score |
| ---- | ------ | ----- |

---

# Task8: Betting Portfolio Optimization

## 目的

資金を最適配分する。

---

## 問題

同レース

```text
単勝
ワイド
馬連
```

に全額投資すると
相関が高い。

---

## 対策

ポートフォリオ最適化

---

## 候補

### Kelly Portfolio

---

### Mean Variance

---

### Risk Parity

---

## 出力

| Ticket | Stake |
| ------ | ----- |

---

# Task9: Strategy Comparison

## 比較対象

### 単勝

---

### ワイド

---

### 馬連

---

### 三連複

---

### Hybrid

---

## 出力

| Strategy | ROI | Hit | Profit |
| -------- | --- | --- | ------ |

---

# Task10: Production Recommendation Engine

## 目的

アプリへ組み込む最終出力作成

---

## 出力例

### 本命

```text
◎ 5番
```

---

### 対抗

```text
○ 11番
```

---

### 単勝

```text
5番
```

---

### ワイド

```text
5-11
```

---

### 馬連

```text
5-11
```

---

### 三連複

```text
5-11-14
```

---

## API

```json
{
  "race_id": "...",
  "recommendations": [...]
}
```

---

# 評価指標

## ROI

最重要

---

## Profit

---

## Hit Rate

---

## Max Drawdown

---

## Sharpe Ratio

---

## Recovery Factor

---

# 成功基準

## 最低

```text
ROI > -5%
```

---

## 目標

```text
ROI >= 0%
```

---

## 理想

```text
ROI > +5%
```

---

# 成果物

## モデル

* top3_model.pkl
* race_simulator.pkl
* ev_engine_v2.pkl

---

## データ

* finish_distribution.parquet
* race_simulation.parquet
* ticket_ev.parquet

---

## 分析

* strategy_comparison.csv
* portfolio_analysis.csv

---

## レポート

* phase4_report.md

---

# Phase4完了条件

* Top3確率推定完成
* Race Simulator完成
* ワイドEV算出
* 馬連EV算出
* 三連複EV算出
* ポートフォリオ最適化完成
* 最良馬券種決定

---

# 最終ゴール

競馬予想アプリとして

単なる勝ち馬予想ではなく

「期待値の高い馬券を提案する投資支援システム」

へ進化させる。

---

# Phase4終了後

次フェーズ候補

## Phase5

Real-Time Prediction Platform

* オッズ変動監視
* パドック評価
* SNS分析
* 直前予測更新

## Phase6

Auto Betting Platform

* 資金管理
* 自動購入連携
* 長期収益最適化

# Phase2: Feature Engineering & Model Improvement

## 目的

Phase1でモデルが市場に対して一定の優位性を持つことを確認できた場合、次の目標は予測精度の向上ではなく、

**市場がまだ十分に織り込めていない情報をモデルへ追加すること**

である。

現状の分析では

* latest_win_odds が特徴量重要度1位
* モデルが市場オッズへ強く依存
* 独自情報による優位性が不足

という可能性が高い。

Phase2では特徴量の質を改善し、市場との差分を発見するモデルを構築する。

---

# 現状整理

## 課題

SHAP上位

| Rank | Feature         |
| ---- | --------------- |
| 1    | latest_win_odds |
| 2    | ???             |
| 3    | ???             |

オッズ依存状態になっている可能性がある。

理想は

| Rank | Feature           |
| ---- | ----------------- |
| 1    | Course Form       |
| 2    | Distance Aptitude |
| 3    | Pace Match        |
| 4    | Surface Aptitude  |
| 5    | Jockey Form       |

である。

---

# Task1: SHAP分析

## 目的

モデルが何を見て予測しているか把握する。

---

## 実施内容

全学習データに対して

```python
shap.TreeExplainer(model)
```

を実行する。

---

## 出力

### Feature Importance

上位50特徴量

| Rank | Feature | SHAP |
| ---- | ------- | ---- |
| 1    |         |      |
| 2    |         |      |
| 3    |         |      |

---

### SHAP Summary Plot

作成ファイル

```text
shap_summary.png
```

---

### SHAP Dependence Plot

対象

* latest_win_odds
* popularity
* course_form

---

## 判断基準

### 危険

オッズ系特徴量が50%以上占有

---

### 理想

複数カテゴリがバランス良く寄与

---

# Task2: コース適性特徴量

## 目的

競馬で最も重要な要素の一つ。

同距離・同競馬場・同回りでの実績を定量化する。

---

## 作成特徴量

### Course Win Rate

```text
東京芝1600
中山芝1200
阪神ダ1800
```

ごとの勝率

---

### Course In-the-Money Rate

3着以内率

---

### Course ROI

過去同条件回収率

---

### Same Track Performance

同競馬場実績

---

### Same Distance Performance

同距離実績

---

## 出力

```text
course_features.parquet
```

---

# Task3: 距離適性特徴量

## 目的

距離適性を数値化する。

---

## 作成特徴量

### 平均着順

距離別

---

### 平均上がり順位

距離別

---

### 勝率

距離別

---

### 距離変化

```text
前走1200m
今回1600m

+400m
```

---

### 距離適性指数

独自指標

```text
distance_score
```

---

# Task4: 馬場適性特徴量

## 目的

良馬場だけ強い馬と重馬場巧者を分離する。

---

## 作成特徴量

### Surface Win Rate

* 良
* 稍重
* 重
* 不良

---

### Surface ROI

馬場別回収率

---

### 芝ダート変化

```text
芝→ダート
ダート→芝
```

---

### Heavy Track Score

重馬場指数

---

# Task5: 騎手特徴量

## 目的

市場が十分評価できていない騎手効果を抽出する。

---

## 作成特徴量

### 騎手勝率

過去365日

---

### 騎手連対率

過去365日

---

### 騎手ROI

過去365日

---

### コース別騎手成績

例

```text
ルメール × 東京芝1600
```

---

### 騎手乗り替わり

```text
upgrade_jockey
downgrade_jockey
```

---

# Task6: 厩舎特徴量

## 目的

厩舎状態を数値化する。

---

## 作成特徴量

### 厩舎勝率

30日

90日

365日

---

### 厩舎ROI

期間別

---

### 厩舎連対率

期間別

---

### 騎手×厩舎コンビ

コンビ勝率

---

# Task7: ペース特徴量

## 目的

市場が最も苦手な領域。

高期待値候補。

---

## 作成特徴量

### 脚質

* 逃げ
* 先行
* 差し
* 追込

---

### レース脚質分布

例

```text
逃げ 4頭
先行 8頭
差し 3頭
追込 2頭
```

---

### Pace Prediction

```text
Slow
Middle
High
```

---

### Pace Advantage Score

各馬の展開利指数

---

## 優先度

★★★★★

---

# Task8: 休養・ローテーション特徴量

## 目的

コンディション変化を数値化する。

---

## 作成特徴量

### Days Since Last Race

前走からの日数

---

### Long Break Flag

90日以上

---

### Short Turnaround Flag

14日以内

---

### Seasonal Performance

春夏秋冬成績

---

# Task9: 新モデル学習

## 候補

### LightGBM Ranker

現行改善版

---

### LambdaMART

ランキング特化

---

### CatBoost Ranker

カテゴリ特徴量対応

---

## 学習方法

単純分類ではなく

```text
race_id
↓
race group
↓
ranking
```

として学習

---

# 評価指標

## 主指標

ROI

---

## 副指標

* Hit Rate
* Precision@1
* NDCG
* LogLoss
* Brier Score

---

# 成功基準

## 最低ライン

ROI

```text
-19.6%
↓
-15%
以内
```

---

## 目標

```text
-10%
以内
```

---

## 理想

```text
-5%
以内
```

---

# Phase2成果物

## データ

* course_features.parquet
* distance_features.parquet
* surface_features.parquet
* jockey_features.parquet
* trainer_features.parquet
* pace_features.parquet

---

## 分析

* shap_summary.png
* shap_importance.csv
* feature_correlation.csv

---

## モデル

* lgbm_ranker_v2.pkl
* catboost_ranker.pkl
* model_report.md

---

# Phase2完了条件

以下を満たすこと。

* SHAP分析完了
* コース適性特徴量実装
* 距離適性特徴量実装
* 馬場適性特徴量実装
* 騎手特徴量実装
* 厩舎特徴量実装
* ペース特徴量実装
* Ranker再学習完了
* ROI改善確認

---

# Phase2終了時の判断

## ROI改善あり

市場に対する優位性を確認

→ Phase3へ進む

---

## ROI改善なし

特徴量ではなく学習戦略が問題

→

* EV学習
* Profit Learning
* Reinforcement Learning

を検討する

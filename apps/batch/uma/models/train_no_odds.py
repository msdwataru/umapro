"""
オッズ特徴量を除外した LightGBM Ranker の学習・評価スクリプト。

目的:
  latest_win_odds / odds_inv / odds_rank をすべて除外し、
  「競走成績のみ」でどれだけ予測できるか検証する。

  Walk-Forward fold5 (train=2020-2025, val=2026-01-15以降) で評価。
  Phase0 metrics_lib によるブロックブートストラップ CI・p値を付与。

Usage:
    cd apps/batch
    python -m uma.models.train_no_odds
    python -m uma.models.train_no_odds --n-estimators 1000 --val-from 20260115
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import ndcg_score

from uma.db.client import get_client
from uma.jobs.base import job_context
from uma.phase0.metrics_lib import roi_ci, roi_significance, format_roi_row, drawdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"
_PARQUET_PATH  = _ARTIFACTS_DIR / "race_features_v1.parquet"
_MODEL_PATH    = _ARTIFACTS_DIR / "lgbm_ranker_no_odds_v1.txt"
_OUT_DIR       = _ARTIFACTS_DIR / "no_odds_eval"

_MODEL_NAME    = "lgbm_ranker_no_odds"
_MODEL_VERSION = "v1"
STAKE          = 100.0

# ── 除外カラム ────────────────────────────────────────────────────────
_BASE_EXCLUDE = {
    "race_entry_id", "race_id", "race_date",
    "finish_position", "finish_time_sec",
    "jockey_affiliation_enc",
}

# オッズ関連特徴量（除外対象）
_ODDS_COLS = {
    "latest_win_odds",
    "odds_inv",
    "odds_rank",
}

_CAT_COLS = ["sire_name", "dam_name"]

_DEFAULT_PARAMS = dict(
    objective        = "rank_xendcg",
    metric           = "rmse",
    learning_rate    = 0.05,
    num_leaves       = 63,
    min_child_samples = 5,
    subsample        = 0.8,
    colsample_bytree = 0.8,
    reg_alpha        = 0.1,
    reg_lambda       = 0.1,
    random_state     = 42,
    n_jobs           = -1,
    verbose          = -1,
)


# ──────────────────────────────────────────────────────────────────────
# データ準備
# ──────────────────────────────────────────────────────────────────────

def _load(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    df = df[df["finish_position"].notna()].copy()
    df = df.sort_values(["race_date", "race_id", "finish_position"]).reset_index(drop=True)
    logger.info("Loaded: %d rows × %d cols", len(df), len(df.columns))
    return df


def _feature_cols(df: pd.DataFrame) -> list[str]:
    exclude = _BASE_EXCLUDE | _ODDS_COLS
    cols = [c for c in df.columns if c not in exclude]
    return cols


def _make_target(df: pd.DataFrame) -> np.ndarray:
    return ((df["field_size"] + 1 - df["finish_position"]) / df["field_size"]).values


def _group_sizes(df: pd.DataFrame) -> np.ndarray:
    return df.groupby("race_id", sort=False).size().values


def _encode_cat(df: pd.DataFrame) -> pd.DataFrame:
    for col in _CAT_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


# ──────────────────────────────────────────────────────────────────────
# 予測確率の生成（softmax 正規化）
# ──────────────────────────────────────────────────────────────────────

def _predict_proba(model: lgb.Booster, df: pd.DataFrame, feat_cols: list[str]) -> np.ndarray:
    """
    スコアを softmax でレース内正規化し、勝率推定値として返す。
    df は reset_index(drop=True) 済みであること（0 ベースの loc が必要）。
    """
    scores = model.predict(df[feat_cols])
    proba  = np.zeros(len(df))
    for _, grp in df.groupby("race_id", sort=False):
        idx   = grp.index.values        # 0 ベースの整数位置
        s     = scores[idx]
        s_exp = np.exp(s - s.max())
        proba[idx] = s_exp / s_exp.sum()
    return proba


# ──────────────────────────────────────────────────────────────────────
# ランキング評価指標
# ──────────────────────────────────────────────────────────────────────

def _eval_ranking(df: pd.DataFrame, scores: np.ndarray) -> dict:
    df = df.copy()
    df["_score"] = scores
    df["_tgt"]   = _make_target(df)

    win_hits, top3_hits, ndcg1_list, ndcg3_list = [], [], [], []
    for _, grp in df.groupby("race_id", sort=False):
        if len(grp) < 2:
            continue
        sc  = grp["_score"].values
        tgt = grp["_tgt"].values
        pos = grp["finish_position"].values
        pred_top = np.argsort(sc)[::-1]
        win_hits.append(int(pos[pred_top[0]] == 1))
        top3_hits.append(int(any(pos[i] == 1 for i in pred_top[:3])))
        ndcg1_list.append(float(ndcg_score([tgt], [sc], k=1)))
        ndcg3_list.append(float(ndcg_score([tgt], [sc], k=3)))

    return {
        "win_acc":   round(float(np.mean(win_hits)),   4),
        "top3_acc":  round(float(np.mean(top3_hits)),  4),
        "ndcg_at_1": round(float(np.mean(ndcg1_list)), 4),
        "ndcg_at_3": round(float(np.mean(ndcg3_list)), 4),
        "n_races":   len(win_hits),
    }


# ──────────────────────────────────────────────────────────────────────
# ROI 評価（予測 rank-1 馬を全レース購入）
# ──────────────────────────────────────────────────────────────────────

def _eval_roi(df: pd.DataFrame, proba: np.ndarray) -> dict:
    """
    各レースで predicted_proba が最大の馬を購入した場合の ROI を計算する。
    payout は latest_win_odds × STAKE（OPTIMISTIC_BIAS）。
    """
    df = df.copy()
    df["_proba"] = proba

    bets = []
    for _, grp in df.groupby("race_id", sort=False):
        top_idx  = grp["_proba"].idxmax()
        chosen   = grp.loc[top_idx]
        won      = chosen["finish_position"] == 1
        payout   = chosen["latest_win_odds"] * STAKE if won else 0.0
        bets.append({
            "race_id":      chosen["race_id"],
            "odds_rank":    chosen["odds_rank"],       # 実際の人気
            "latest_odds":  chosen["latest_win_odds"],
            "finish_pos":   chosen["finish_position"],
            "is_win":       won,
            "payout":       payout,
            "profit":       payout - STAKE,
        })

    bets_df  = pd.DataFrame(bets)
    profits  = bets_df["profit"].values
    stakes   = np.full(len(bets_df), STAKE)
    race_ids = bets_df["race_id"].values

    result = roi_ci(profits, stakes, race_ids=race_ids)
    p_val  = roi_significance(profits, stakes, race_ids=race_ids, null_roi=0.0)

    result["bets_df"] = bets_df
    result["p_value"] = p_val
    return result


# ──────────────────────────────────────────────────────────────────────
# キャリブレーション分析
# ──────────────────────────────────────────────────────────────────────

def _eval_calibration(df: pd.DataFrame, proba: np.ndarray) -> pd.DataFrame:
    df = df.copy()
    df["_proba"] = proba
    bins = list(range(0, 55, 5))   # 0, 5, 10, ..., 50
    labels = [f"{b}%〜{b+5}%" for b in bins[:-1]]
    df["_bin"] = pd.cut(df["_proba"] * 100, bins=bins, labels=labels, right=False)

    rows = []
    for label, grp in df.groupby("_bin", observed=True, sort=True):
        n      = len(grp)
        actual = (grp["finish_position"] == 1).mean()
        pred   = grp["_proba"].mean()
        rows.append({
            "bin":          str(label),
            "n":            n,
            "pred_prob":    round(float(pred),   4),
            "actual_win":   round(float(actual), 4),
            "error":        round(abs(float(actual) - float(pred)), 4),
        })

    cal_df = pd.DataFrame(rows)
    total  = cal_df["n"].sum()
    ece    = (cal_df["n"] / total * cal_df["error"]).sum() if total > 0 else np.nan
    cal_df.attrs["ece"] = round(float(ece), 4)
    return cal_df


# ──────────────────────────────────────────────────────────────────────
# ベースライン比較
# ──────────────────────────────────────────────────────────────────────

def _eval_baselines(df: pd.DataFrame, proba: np.ndarray) -> pd.DataFrame:
    """
    Random / Favorite / Market / no-odds Model の ROI を一表にまとめる。
    """
    rows = []

    # Random（Monte Carlo 100回）
    rng = np.random.default_rng(42)
    rand_profits, rand_stakes, rand_rids = [], [], []
    races = df["race_id"].unique()
    for _ in range(100):
        for rid in races:
            grp = df[df["race_id"] == rid]
            if len(grp) == 0:
                continue
            ch  = grp.sample(1, random_state=int(rng.integers(0, 10**7))).iloc[0]
            won = ch["finish_position"] == 1
            rand_profits.append(((ch["latest_win_odds"] * STAKE - STAKE) if won else -STAKE) / 100)
            rand_stakes.append(STAKE / 100)
            rand_rids.append(rid)
    r_rand = roi_ci(np.array(rand_profits), np.array(rand_stakes), race_ids=np.array(rand_rids))
    rows.append(format_roi_row("Random（ランダム）", r_rand))

    # Favorite（1番人気）
    favs = df[df["odds_rank"] == 1]
    fav_won     = favs["finish_position"] == 1
    fav_profits = np.where(fav_won, favs["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_fav = roi_ci(fav_profits, np.full(len(favs), STAKE), race_ids=favs["race_id"].values)
    p_fav = roi_significance(fav_profits, np.full(len(favs), STAKE), race_ids=favs["race_id"].values)
    rows.append(format_roi_row("Favorite（1番人気）", r_fav, p_value=p_fav))

    # Market（1/odds 正規化後 最大確率馬）
    df2 = df.copy()
    df2["_oi"] = 1.0 / df2["latest_win_odds"]
    df2["_mp"] = df2.groupby("race_id")["_oi"].transform(lambda x: x / x.sum())
    mkt_idx    = df2.groupby("race_id")["_mp"].idxmax()
    mkt        = df2.loc[mkt_idx]
    mkt_won    = mkt["finish_position"] == 1
    mkt_profits = np.where(mkt_won, mkt["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_mkt = roi_ci(mkt_profits, np.full(len(mkt), STAKE), race_ids=mkt["race_id"].values)
    p_mkt = roi_significance(mkt_profits, np.full(len(mkt), STAKE), race_ids=mkt["race_id"].values)
    market_roi = r_mkt["roi"]
    rows.append(format_roi_row("Market（市場確率最大）★天井", r_mkt, p_value=p_mkt))

    # No-odds Model（本モデル）
    df3       = df.copy()
    df3["_p"] = proba
    model_idx = df3.groupby("race_id")["_p"].idxmax()
    model_ch  = df3.loc[model_idx]
    m_won     = model_ch["finish_position"] == 1
    m_profits = np.where(m_won, model_ch["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_model = roi_ci(m_profits, np.full(len(model_ch), STAKE), race_ids=model_ch["race_id"].values)
    p_model = roi_significance(m_profits, np.full(len(model_ch), STAKE),
                               race_ids=model_ch["race_id"].values,
                               null_roi=market_roi)
    rows.append(format_roi_row(
        "no-odds LightGBM Ranker",
        r_model,
        p_value=p_model,
        reference_roi=market_roi,
    ))

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────
# 人気別 ROI（モデル予測 rank-1 馬が何番人気か）
# ──────────────────────────────────────────────────────────────────────

def _popularity_roi(bets_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pop, grp in bets_df.groupby("odds_rank"):
        n   = len(grp)
        if n < 5:
            continue
        won = grp["is_win"].sum()
        roi_val = grp["payout"].sum() / (n * STAKE)
        rows.append({
            "odds_rank": int(pop),
            "n_bets":    n,
            "n_win":     int(won),
            "hit_rate":  round(won / n, 4),
            "roi":       round(roi_val, 4),
        })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────
# DB 登録
# ──────────────────────────────────────────────────────────────────────

def _register_model(client, feat_cols: list[str], train_df: pd.DataFrame,
                    val_df: pd.DataFrame, ranking_metrics: dict, best_iter: int) -> int:
    try:
        fs = (client.table("feature_sets").select("id")
              .eq("feature_set_name", "lgbm_ranker_v1").eq("version", "v1")
              .single().execute())
        fs_id = fs.data["id"]
    except Exception:
        fs_id = 9  # fallback

    metrics = {
        "best_iteration":  best_iter,
        "n_features":      len(feat_cols),
        "n_train_rows":    int(len(train_df)),
        "n_val_rows":      int(len(val_df)),
        "odds_excluded":   True,
        "odds_cols_removed": list(_ODDS_COLS),
        "train": {k: v for k, v in ranking_metrics.items() if k != "n_races"},
    }

    r = (client.table("model_versions")
         .upsert({
             "model_name":            _MODEL_NAME,
             "version":               _MODEL_VERSION,
             "model_type":            "ranker",
             "feature_set_id":        fs_id,
             "training_period_start": train_df["race_date"].min(),
             "training_period_end":   train_df["race_date"].max(),
             "metrics_json":          metrics,
             "artifact_path":         str(_MODEL_PATH),
             "is_production":         False,
         }, on_conflict="model_name,version")
         .execute())
    return r.data[0]["id"]


# ──────────────────────────────────────────────────────────────────────
# レポート生成
# ──────────────────────────────────────────────────────────────────────

def _generate_report(
    ranking_metrics: dict,
    roi_result: dict,
    cal_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
    pop_df: pd.DataFrame,
    fi_series: pd.Series,
    val_period: str,
    feat_cols: list[str],
    out_dir: Path,
) -> None:
    ece   = cal_df.attrs.get("ece", "N/A")
    n_bets = roi_result.get("n_bets", 0)
    roi_pct = roi_result.get("roi", np.nan)
    ci_low  = roi_result.get("ci_low",  np.nan)
    ci_high = roi_result.get("ci_high", np.nan)
    p_val   = roi_result.get("p_value", 1.0)

    baseline_md = "| Strategy | 購入数 | ROI | 95% CI | p値 | 有意 | Marketとの差 |\n"
    baseline_md += "|---|---|---|---|---|---|---|\n"
    for row in baseline_df.to_dict("records"):
        sig = "✅" if row.get("significant") else "❌"
        vs  = f"{row.get('vs_reference_pt', '-'):+.2f}pt" if row.get("vs_reference_pt") is not None else "-"
        reliable_flag = "" if row.get("reliable", True) else " ⚠️"
        baseline_md += (
            f"| {row.get('label','')} | {row.get('n_bets',0)}{reliable_flag} "
            f"| {row.get('roi_pct','N/A')}% "
            f"| [{row.get('ci_low_pct','?')}%, {row.get('ci_high_pct','?')}%] "
            f"| {row.get('p_value', '-')} | {sig} | {vs} |\n"
        )

    cal_md = "| 予測確率帯 | 件数 | 予測確率 | 実勝率 | 誤差 |\n|---|---|---|---|---|\n"
    for _, r in cal_df.iterrows():
        cal_md += f"| {r['bin']} | {r['n']} | {r['pred_prob']:.4f} | {r['actual_win']:.4f} | {r['error']:.4f} |\n"

    pop_md = "| 人気 | 購入数 | 的中数 | 的中率 | ROI |\n|---|---|---|---|---|\n"
    for _, r in pop_df.iterrows():
        pop_md += f"| {r['odds_rank']:.0f} | {r['n_bets']} | {r['n_win']} | {r['hit_rate']:.3f} | {r['roi']:.4f} |\n"

    fi_md = "| Rank | 特徴量 | Importance |\n|---|---|---|\n"
    for i, (name, val) in enumerate(fi_series.head(20).items(), 1):
        fi_md += f"| {i} | {name} | {val:.0f} |\n"

    # 判定
    market_row = next((r for r in baseline_df.to_dict("records") if "Market" in str(r.get("label", ""))), None)
    model_row  = next((r for r in baseline_df.to_dict("records") if "no-odds" in str(r.get("label", ""))), None)

    if market_row and model_row:
        vs_market = model_row.get("vs_reference_pt") or 0
        sig       = model_row.get("significant", False)
        if sig and vs_market > 0:
            judgment = f"**A — Market を {vs_market:+.2f}pt 上回る（有意）✅**\n→ オッズなしモデルに市場に対する優位性あり"
        elif vs_market > 0:
            judgment = f"**B — Market を {vs_market:+.2f}pt 上回るが有意差なし ⚠️**\n→ サンプル数不足の可能性。データ蓄積後に再評価"
        else:
            judgment = f"**C — Market を {vs_market:+.2f}pt 下回る ❌**\n→ 非オッズ特徴量のみでは市場を出し抜けない"
    else:
        judgment = "判定不能"

    report = f"""# オッズなし LightGBM Ranker — 評価レポート

**評価期間**: {val_period}（Walk-Forward Fold5 out-of-sample）
**除外特徴量**: `latest_win_odds`, `odds_inv`, `odds_rank`
**使用特徴量数**: {len(feat_cols)}
> ⚠️ OPTIMISTIC_BIAS: payout は `latest_win_odds`（確定オッズ近似値）で計算。

---

## ランキング指標（val={val_period}）

| 指標 | 値 |
|---|---|
| win_acc（予測1位が1着の割合） | {ranking_metrics['win_acc']:.3f} |
| top3_acc（1着が予測top3内） | {ranking_metrics['top3_acc']:.3f} |
| NDCG@1 | {ranking_metrics['ndcg_at_1']:.4f} |
| NDCG@3 | {ranking_metrics['ndcg_at_3']:.4f} |
| 評価レース数 | {ranking_metrics['n_races']:,} |

---

## ROI（予測確率最大の馬を全レース購入）

| 指標 | 値 |
|---|---|
| 購入数 | {n_bets:,} |
| ROI | {roi_pct*100:.2f}% |
| 95% CI | [{ci_low*100:.2f}%, {ci_high*100:.2f}%] |
| p値（H0: ROI <= 0%） | {p_val:.4f} |
| 有意 | {"✅" if p_val < 0.05 else "❌"} |

---

## ベースライン比較

{baseline_md}

---

## キャリブレーション分析

**ECE (Expected Calibration Error)**: {ece}

{cal_md}

> ECE が小さいほど予測確率と実際の勝率が一致している。

---

## 人気別ROI（モデルが何番人気の馬を推奨しているか）

{pop_md}

---

## 特徴量重要度 Top20

{fi_md}

---

## Phase0 総合判定

{judgment}

---

## 現行モデル（lgbm_ranker_v1）との比較

| 項目 | 現行（オッズあり） | 今回（オッズなし） |
|---|---|---|
| 特徴量数 | 63 | {len(feat_cols)} |
| 2026 ROI | -22.8% | {roi_pct*100:.2f}% |
| Market 超過 | ❌ | {"✅" if (model_row or {}).get("significant") else "❌"} |

"""

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "no_odds_report.md").write_text(report, encoding="utf-8")
    logger.info("レポート保存: %s", out_dir / "no_odds_report.md")


# ──────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="オッズなし LightGBM Ranker 学習・評価")
    parser.add_argument("--val-from", default="20260115", metavar="YYYYMMDD",
                        help="検証開始日（Walk-Forward fold5 embargo 後）")
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--early-stopping", type=int, default=50)
    parser.add_argument("--parquet", default=str(_PARQUET_PATH))
    args = parser.parse_args()

    val_from = datetime.strptime(args.val_from, "%Y%m%d").strftime("%Y-%m-%d")

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = get_client()

    with job_context("train_lgbm_ranker_no_odds", "train") as ctx:
        # ── データ ──────────────────────────────────────────────────
        df = _load(Path(args.parquet))
        df = _encode_cat(df)

        feat_cols = _feature_cols(df)
        logger.info("Feature cols: %d (odds cols 除外済み)", len(feat_cols))
        logger.info("除外オッズ列: %s", sorted(_ODDS_COLS))

        # ── 時系列分割（fold5: train < val_from, val >= val_from） ──
        train_mask = df["race_date"] < val_from
        val_mask   = df["race_date"] >= val_from
        df_train   = df[train_mask].reset_index(drop=True)
        df_val     = df[val_mask].reset_index(drop=True)

        logger.info(
            "分割: train=%d行/%dレース  val=%d行/%dレース",
            len(df_train), df_train["race_id"].nunique(),
            len(df_val),   df_val["race_id"].nunique(),
        )

        if len(df_train) == 0:
            raise ValueError("訓練データが0件。--val-from の日付を確認してください。")

        X_train = df_train[feat_cols]
        y_train = _make_target(df_train)
        g_train = _group_sizes(df_train)

        X_val   = df_val[feat_cols]
        y_val   = _make_target(df_val)
        g_val   = _group_sizes(df_val)

        # ── 学習 ─────────────────────────────────────────────────────
        params = {**_DEFAULT_PARAMS, "n_estimators": args.n_estimators}
        ranker = lgb.LGBMRanker(**params)

        callbacks = [lgb.log_evaluation(50)]
        if args.early_stopping > 0:
            callbacks.append(lgb.early_stopping(args.early_stopping, verbose=True))

        logger.info("学習開始 (n_estimators=%d)...", args.n_estimators)
        ranker.fit(
            X_train, y_train,
            group=g_train,
            eval_set=[(X_val, y_val)],
            eval_group=[g_val],
            categorical_feature=[c for c in _CAT_COLS if c in feat_cols],
            callbacks=callbacks,
        )

        best_iter = ranker.best_iteration_ or args.n_estimators
        logger.info("学習完了 best_iteration=%d", best_iter)

        # ── 保存 ──────────────────────────────────────────────────────
        _ARTIFACTS_DIR.mkdir(exist_ok=True)
        ranker.booster_.save_model(str(_MODEL_PATH))
        logger.info("モデル保存: %s", _MODEL_PATH)

        # ── ランキング評価 ───────────────────────────────────────────
        val_scores  = ranker.booster_.predict(X_val)
        ranking_m   = _eval_ranking(df_val, val_scores)
        logger.info("ランキング指標: %s", ranking_m)

        train_scores = ranker.booster_.predict(X_train)
        train_m      = _eval_ranking(df_train, train_scores)
        logger.info("Train指標: %s", train_m)

        # ── 予測確率（softmax 正規化） ───────────────────────────────
        proba = _predict_proba(ranker.booster_, df_val, feat_cols)

        # ── ROI 評価 ─────────────────────────────────────────────────
        roi_result = _eval_roi(df_val, proba)
        logger.info(
            "ROI: %.2f%%  CI=[%.2f%%, %.2f%%]  p=%.4f",
            roi_result["roi"] * 100,
            roi_result["ci_low"] * 100,
            roi_result["ci_high"] * 100,
            roi_result["p_value"],
        )

        # ── キャリブレーション ───────────────────────────────────────
        cal_df = _eval_calibration(df_val, proba)
        logger.info("ECE=%.4f", cal_df.attrs.get("ece"))
        cal_df.to_csv(_OUT_DIR / "calibration.csv", index=False, encoding="utf-8-sig")

        # ── ベースライン比較 ─────────────────────────────────────────
        baseline_df = _eval_baselines(df_val, proba)
        baseline_df.to_csv(_OUT_DIR / "baseline_comparison.csv", index=False, encoding="utf-8-sig")

        # ── 人気別 ROI ───────────────────────────────────────────────
        pop_df = _popularity_roi(roi_result["bets_df"])
        pop_df.to_csv(_OUT_DIR / "popularity_roi.csv", index=False, encoding="utf-8-sig")

        # ── 特徴量重要度 ─────────────────────────────────────────────
        fi = pd.Series(ranker.feature_importances_, index=feat_cols).sort_values(ascending=False)
        fi.to_csv(_OUT_DIR / "feature_importance.csv", header=["importance"], encoding="utf-8-sig")
        logger.info("特徴量重要度 top-10:\n%s", fi.head(10).to_string())

        # ── DB 登録 ───────────────────────────────────────────────────
        mv_id = _register_model(client, feat_cols, df_train, df_val, ranking_m, best_iter)
        logger.info("model_versions 登録: id=%d", mv_id)

        # ── レポート ─────────────────────────────────────────────────
        _generate_report(
            ranking_metrics = ranking_m,
            roi_result      = roi_result,
            cal_df          = cal_df,
            baseline_df     = baseline_df,
            pop_df          = pop_df,
            fi_series       = fi,
            val_period      = f"{val_from}〜",
            feat_cols       = feat_cols,
            out_dir         = _OUT_DIR,
        )

        ctx["records_processed"] = len(df_train) + len(df_val)

    # ── サマリー出力 ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("オッズなし LightGBM Ranker — 学習・評価完了")
    print(f"  モデルパス   : {_MODEL_PATH}")
    print(f"  best_iter    : {best_iter}")
    print(f"  訓練         : {len(df_train):,}行 / {df_train['race_id'].nunique():,}レース")
    print(f"  検証(2026)   : {len(df_val):,}行 / {df_val['race_id'].nunique():,}レース")
    print(f"\n  【ランキング指標】")
    print(f"    win_acc    : {ranking_m['win_acc']:.3f}")
    print(f"    top3_acc   : {ranking_m['top3_acc']:.3f}")
    print(f"    NDCG@1     : {ranking_m['ndcg_at_1']:.4f}")
    print(f"\n  【ROI（val, 全レース rank-1 購入）】")
    print(f"    ROI        : {roi_result['roi']*100:.2f}%")
    print(f"    95% CI     : [{roi_result['ci_low']*100:.2f}%, {roi_result['ci_high']*100:.2f}%]")
    print(f"    p値        : {roi_result['p_value']:.4f}")
    print(f"    ECE        : {cal_df.attrs.get('ece')}")
    print(f"\n  【特徴量重要度 top-10】")
    for name, score in fi.head(10).items():
        print(f"    {name:<40} {score:>6.0f}")
    print(f"\n  レポート出力: {_OUT_DIR}/no_odds_report.md")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

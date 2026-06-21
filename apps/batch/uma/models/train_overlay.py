"""
Overlay 直接ターゲット学習

Binary B（odds除外）の延長として、市場との乖離（Overlay）を直接回帰ターゲットにする。

target  = is_win(0/1) - market_prob
          正: 市場が過小評価している馬
          負: 市場が過大評価している馬
features = odds系除外の非市場特徴量のみ

パターン:
  D: regression (RMSE)
  E: huber 回帰（外れ値頑健、高配当外れの引っ張りを緩和）

賭け戦略:
  top     : 各レースで予測Overlay 最大の馬に常時購入
  positive: 予測Overlay > 0（市場より高く評価）の場合のみ購入

Usage:
    cd apps/batch
    python -m uma.models.train_overlay
    python -m uma.models.train_overlay --val-from 20260115 --n-estimators 500
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, mean_absolute_error

from uma.jobs.base import job_context
from uma.phase0.metrics_lib import roi_ci, roi_significance, format_roi_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"
_PARQUET_PATH  = _ARTIFACTS_DIR / "race_features_v1.parquet"
_OUT_DIR       = _ARTIFACTS_DIR / "overlay_eval"

STAKE = 100.0

_BASE_EXCLUDE = {
    "race_entry_id", "race_id", "race_date",
    "finish_position", "finish_time_sec",
    "jockey_affiliation_enc",
    "market_prob", "overlay_target",
}
_ODDS_COLS = {"latest_win_odds", "odds_inv", "odds_rank"}
_CAT_COLS  = ["sire_name", "dam_name"]

_REG_BASE = dict(
    learning_rate     = 0.05,
    num_leaves        = 63,
    min_child_samples = 10,
    subsample         = 0.8,
    colsample_bytree  = 0.8,
    reg_alpha         = 0.1,
    reg_lambda        = 0.1,
    random_state      = 42,
    n_jobs            = -1,
    verbose           = -1,
)


# ──────────────────────────────────────────────────────────────────────
# データ準備
# ──────────────────────────────────────────────────────────────────────

def _load(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    df = df[df["finish_position"].notna()].copy()
    # finish_position / race_entry_id でソートしてはいけない:
    # race_entry_id は着順に採番されるため、idxmax() タイブレークが常に1着馬を選ぶ
    # horse_number（レース前の枠順抽選番号）は結果と無相関なので中立なソートキーになる
    df = df.sort_values(["race_date", "race_id", "horse_number"]).reset_index(drop=True)
    # market_prob = 1/odds 正規化（レース内合計=1）
    df["market_prob"] = df.groupby("race_id")["odds_inv"].transform(lambda x: x / x.sum())
    # overlay_target = 実勝敗 - 市場確率（正=市場過小評価）
    df["overlay_target"] = (df["finish_position"] == 1).astype(float) - df["market_prob"]
    logger.info("Loaded: %d rows x %d cols", len(df), len(df.columns))
    return df


def _encode_cat(df: pd.DataFrame) -> pd.DataFrame:
    for col in _CAT_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


def _feat_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in (_BASE_EXCLUDE | _ODDS_COLS)]


# ──────────────────────────────────────────────────────────────────────
# ROI 評価
# ──────────────────────────────────────────────────────────────────────

def _eval_roi(df: pd.DataFrame, pred_overlay: np.ndarray, strategy: str) -> dict:
    """
    strategy:
      "top"      : 各レースで最高予測Overlay の馬に常時購入
      "positive" : 最高予測Overlay > 0 の場合のみ購入（負なら不購入）
    """
    df = df.copy()
    df["_pred"] = pred_overlay

    bets = []
    for _, grp in df.groupby("race_id", sort=False):
        top_idx = grp["_pred"].idxmax()
        chosen  = grp.loc[top_idx]
        if strategy == "positive" and chosen["_pred"] <= 0:
            continue
        won = chosen["finish_position"] == 1
        bets.append({
            "race_id":        chosen["race_id"],
            "odds":           chosen["latest_win_odds"],
            "pred_overlay":   chosen["_pred"],
            "actual_overlay": chosen["overlay_target"],
            "market_prob":    chosen["market_prob"],
            "is_win":         bool(won),
            "profit":         chosen["latest_win_odds"] * STAKE - STAKE if won else -STAKE,
        })

    if not bets:
        return {
            "roi": np.nan, "ci_low": np.nan, "ci_high": np.nan,
            "n_bets": 0, "p_value": np.nan,
            "total_profit": 0.0, "total_stake": 0.0,
            "bets_df": pd.DataFrame(),
        }

    bets_df  = pd.DataFrame(bets)
    profits  = bets_df["profit"].values
    stakes   = np.full(len(bets_df), STAKE)
    race_ids = bets_df["race_id"].values

    r = roi_ci(profits, stakes, race_ids=race_ids)
    r["p_value"] = roi_significance(profits, stakes, race_ids=race_ids)
    r["bets_df"] = bets_df
    return r


def _overlay_threshold_roi(df: pd.DataFrame, pred_overlay: np.ndarray) -> pd.DataFrame:
    """各レースの最高予測Overlay 馬を候補として、予測Overlay しきい値別ROI を集計する。"""
    df = df.copy()
    df["_pred"] = pred_overlay

    top_idx = df.groupby("race_id")["_pred"].idxmax()
    bets    = df.loc[top_idx].copy()
    bets["profit"] = np.where(
        bets["finish_position"] == 1,
        bets["latest_win_odds"] * STAKE - STAKE,
        -STAKE,
    )

    thresholds = [0.0, 0.02, 0.05, 0.08, 0.10, 0.15]
    rows = []
    for thr in thresholds:
        subset = bets[bets["_pred"] >= thr]
        n = len(subset)
        if n < 10:
            continue
        profits  = subset["profit"].values
        stakes   = np.full(n, STAKE)
        race_ids = subset["race_id"].values
        r = roi_ci(profits, stakes, race_ids=race_ids)
        p = roi_significance(profits, stakes, race_ids=race_ids)
        rows.append({
            "threshold":   thr,
            "n_bets":      n,
            "hit_rate":    round(float((subset["finish_position"] == 1).mean()), 4),
            "roi_pct":     round(r["roi"] * 100, 2),
            "ci_low":      round(r["ci_low"] * 100, 2),
            "ci_high":     round(r["ci_high"] * 100, 2),
            "p_value":     round(p, 4),
            "significant": p < 0.05,
        })
    return pd.DataFrame(rows)


def _baseline_comparison(df: pd.DataFrame, pred_overlay: np.ndarray, label: str) -> tuple[pd.DataFrame, float]:
    rows = []

    # Favorite
    favs    = df[df["odds_rank"] == 1]
    fav_won = favs["finish_position"] == 1
    fav_p   = np.where(fav_won, favs["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_fav   = roi_ci(fav_p, np.full(len(favs), STAKE), race_ids=favs["race_id"].values)
    p_fav   = roi_significance(fav_p, np.full(len(favs), STAKE), race_ids=favs["race_id"].values)
    rows.append(format_roi_row("Favorite（1番人気）", r_fav, p_value=p_fav))

    # Market
    mkt_idx = df.groupby("race_id")["market_prob"].idxmax()
    mkt     = df.loc[mkt_idx]
    mkt_won = mkt["finish_position"] == 1
    mkt_p   = np.where(mkt_won, mkt["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_mkt   = roi_ci(mkt_p, np.full(len(mkt), STAKE), race_ids=mkt["race_id"].values)
    p_mkt   = roi_significance(mkt_p, np.full(len(mkt), STAKE), race_ids=mkt["race_id"].values)
    market_roi = r_mkt["roi"]
    rows.append(format_roi_row("Market（市場確率最大）★天井", r_mkt, p_value=p_mkt))

    # Model (top overlay per race)
    df2 = df.copy()
    df2["_pred"] = pred_overlay
    top_idx   = df2.groupby("race_id")["_pred"].idxmax()
    model_ch  = df2.loc[top_idx]
    m_won     = model_ch["finish_position"] == 1
    m_profits = np.where(m_won, model_ch["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_model   = roi_ci(m_profits, np.full(len(model_ch), STAKE), race_ids=model_ch["race_id"].values)
    p_model   = roi_significance(
        m_profits, np.full(len(model_ch), STAKE),
        race_ids=model_ch["race_id"].values, null_roi=market_roi,
    )
    rows.append(format_roi_row(label, r_model, p_value=p_model, reference_roi=market_roi))

    return pd.DataFrame(rows), market_roi


# ──────────────────────────────────────────────────────────────────────
# 1モデルの学習・評価
# ──────────────────────────────────────────────────────────────────────

def _run_one(
    label: str,
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    feat_cols: list[str],
    n_estimators: int,
    early_stopping: int,
    objective: str,
    **extra_params,
) -> dict:
    logger.info("=== %s ===", label)
    logger.info("objective=%s  features=%d  train=%d  val=%d",
                objective, len(feat_cols), len(df_train), len(df_val))

    X_train = df_train[feat_cols]
    y_train = df_train["overlay_target"].values
    X_val   = df_val[feat_cols]
    y_val   = df_val["overlay_target"].values

    metric = "rmse" if objective == "regression" else "huber"
    params = {**_REG_BASE, "objective": objective, "metric": metric,
              "n_estimators": n_estimators, **extra_params}

    model = lgb.LGBMRegressor(**params)
    callbacks = [lgb.log_evaluation(50)]
    if early_stopping > 0:
        callbacks.append(lgb.early_stopping(early_stopping, verbose=True))

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        categorical_feature=[c for c in _CAT_COLS if c in feat_cols],
        callbacks=callbacks,
    )

    best_iter = model.best_iteration_ or n_estimators
    logger.info("%s best_iteration=%d", label, best_iter)

    pred_overlay = model.predict(X_val)

    # 回帰メトリクス
    rmse = float(np.sqrt(mean_squared_error(y_val, pred_overlay)))
    mae  = float(mean_absolute_error(y_val, pred_overlay))
    corr = float(np.corrcoef(y_val, pred_overlay)[0, 1]) if len(y_val) > 1 else np.nan
    logger.info("%s RMSE=%.4f  MAE=%.4f  corr(pred,actual)=%.4f", label, rmse, mae, corr)

    # ROI（2戦略）
    roi_top = _eval_roi(df_val, pred_overlay, "top")
    roi_pos = _eval_roi(df_val, pred_overlay, "positive")
    logger.info(
        "%s ROI(top)=%.2f%%  n=%d  |  ROI(positive)=%.2f%%  n=%d",
        label,
        roi_top["roi"] * 100, roi_top["n_bets"],
        roi_pos["roi"] * 100 if not np.isnan(roi_pos["roi"]) else float("nan"),
        roi_pos["n_bets"],
    )

    # Overlay しきい値別 ROI
    overlay_df = _overlay_threshold_roi(df_val, pred_overlay)

    # ベースライン比較
    baseline_df, market_roi = _baseline_comparison(df_val, pred_overlay, label)

    # 特徴量重要度
    fi = pd.Series(model.feature_importances_, index=feat_cols).sort_values(ascending=False)

    return {
        "label":         label,
        "objective":     objective,
        "best_iter":     best_iter,
        "rmse":          rmse,
        "mae":           mae,
        "corr":          corr,
        "roi_top":       roi_top["roi"],
        "ci_low_top":    roi_top["ci_low"],
        "ci_high_top":   roi_top["ci_high"],
        "p_value_top":   roi_top["p_value"],
        "n_bets_top":    roi_top["n_bets"],
        "roi_pos":       roi_pos["roi"],
        "ci_low_pos":    roi_pos["ci_low"],
        "ci_high_pos":   roi_pos["ci_high"],
        "p_value_pos":   roi_pos["p_value"],
        "n_bets_pos":    roi_pos["n_bets"],
        "market_roi":    market_roi,
        "overlay_df":    overlay_df,
        "baseline_df":   baseline_df,
        "bets_df_top":   roi_top["bets_df"],
        "bets_df_pos":   roi_pos["bets_df"],
        "fi":            fi,
        "model":         model,
    }


# ──────────────────────────────────────────────────────────────────────
# レポート生成
# ──────────────────────────────────────────────────────────────────────

def _generate_report(results: list[dict], val_period: str, out_dir: Path) -> None:
    market_roi_pct = round(results[0]["market_roi"] * 100, 2) if results else None

    lines = [
        "# Overlay 直接ターゲット学習 — 評価レポート",
        "",
        f"**評価期間**: {val_period}（Walk-Forward Fold5 out-of-sample）",
        "> ⚠️ OPTIMISTIC_BIAS: ROI は確定オッズ近似値による楽観値。",
        "> target = is_win(0/1) - market_prob  (正=市場過小評価、負=市場過大評価)",
        "> features = odds系除外（latest_win_odds / odds_inv / odds_rank を除去）",
        "",
        "---",
        "",
        "## サマリー比較（Top Overlay 戦略）",
        "",
        "| モデル | best_iter | RMSE | 予測-実相関 | ROI(top) | 95% CI | p値 | Market超過 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        roi_pct = round(r["roi_top"] * 100, 2)
        vs_mkt  = f"{roi_pct - market_roi_pct:+.2f}pt" if market_roi_pct is not None else "-"
        sig = "✅" if r["p_value_top"] < 0.05 else "❌"
        lines.append(
            f"| {r['label']} | {r['best_iter']} "
            f"| {r['rmse']:.4f} | {r['corr']:.4f} "
            f"| {roi_pct}% | [{r['ci_low_top']*100:.2f}%, {r['ci_high_top']*100:.2f}%] "
            f"| {r['p_value_top']:.4f} | {sig} {vs_mkt} |"
        )

    lines += ["", "---", ""]

    for r in results:
        lines += [f"## {r['label']}", ""]

        # 回帰メトリクス
        lines += [
            "### 回帰メトリクス", "",
            "| 指標 | 値 |", "|---|---|",
            f"| RMSE | {r['rmse']:.4f} |",
            f"| MAE | {r['mae']:.4f} |",
            f"| 予測-実相関 | {r['corr']:.4f} |",
            "",
        ]

        # 購入戦略別 ROI
        mkt_pct = round(r["market_roi"] * 100, 2)
        lines += [
            "### 購入戦略別 ROI", "",
            "| 戦略 | n_bets | ROI | 95% CI | p値 | Market比 |",
            "|---|---|---|---|---|---|",
        ]
        for strat, roi_val, ci_l, ci_h, pval, n in [
            ("top（全レース購入）",
             r["roi_top"], r["ci_low_top"], r["ci_high_top"], r["p_value_top"], r["n_bets_top"]),
            ("positive（予測Overlay>0のみ）",
             r["roi_pos"], r["ci_low_pos"], r["ci_high_pos"], r["p_value_pos"], r["n_bets_pos"]),
        ]:
            if np.isnan(roi_val):
                lines.append(f"| {strat} | {n} | N/A | - | - | - |")
            else:
                vs = f"{roi_val*100 - mkt_pct:+.2f}pt"
                lines.append(
                    f"| {strat} | {n} | {roi_val*100:.2f}% "
                    f"| [{ci_l*100:.2f}%, {ci_h*100:.2f}%] | {pval:.4f} | {vs} |"
                )

        # Overlay しきい値別
        lines += ["", "### 予測Overlay しきい値別 ROI", "",
                  "| 予測Overlay >= | 購入数 | 的中率 | ROI | 95% CI | p値 | 有意 |",
                  "|---|---|---|---|---|---|---|"]
        for _, row in r["overlay_df"].iterrows():
            sig = "✅" if row["significant"] else "❌"
            lines.append(
                f"| {row['threshold']:.0%} | {row['n_bets']} "
                f"| {row['hit_rate']:.3f} | {row['roi_pct']}% "
                f"| [{row['ci_low']}%, {row['ci_high']}%] "
                f"| {row['p_value']:.4f} | {sig} |"
            )

        # ベースライン比較
        lines += ["", "### ベースライン比較", "",
                  "| Strategy | 購入数 | ROI | 95% CI | p値 | 有意 | Marketとの差 |",
                  "|---|---|---|---|---|---|---|"]
        for _, row in r["baseline_df"].iterrows():
            sig = "✅" if row.get("significant") else "❌"
            vs  = (f"{row.get('vs_reference_pt'):+.2f}pt"
                   if row.get("vs_reference_pt") is not None else "-")
            lines.append(
                f"| {row['label']} | {row['n_bets']} "
                f"| {row['roi_pct']}% "
                f"| [{row['ci_low_pct']}%, {row['ci_high_pct']}%] "
                f"| {row.get('p_value', '-')} | {sig} | {vs} |"
            )

        # 特徴量重要度 Top10
        lines += ["", "### 特徴量重要度 Top10", "",
                  "| Rank | 特徴量 | Importance |", "|---|---|---|"]
        for i, (name, val) in enumerate(r["fi"].head(10).items(), 1):
            lines.append(f"| {i} | {name} | {val:.0f} |")

        lines += ["", "---", ""]

    report_path = out_dir / "overlay_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("レポート保存: %s", report_path)


# ──────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Overlay 直接ターゲット学習")
    parser.add_argument("--val-from", default="20260115", metavar="YYYYMMDD")
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--early-stopping", type=int, default=50)
    parser.add_argument("--parquet", default=str(_PARQUET_PATH))
    args = parser.parse_args()

    val_from = datetime.strptime(args.val_from, "%Y%m%d").strftime("%Y-%m-%d")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    with job_context("train_overlay", "train") as ctx:
        df = _load(Path(args.parquet))
        df = _encode_cat(df)

        df_train = df[df["race_date"] < val_from].reset_index(drop=True)
        df_val   = df[df["race_date"] >= val_from].reset_index(drop=True)

        logger.info(
            "分割: train=%d行/%dレース  val=%d行/%dレース",
            len(df_train), df_train["race_id"].nunique(),
            len(df_val),   df_val["race_id"].nunique(),
        )

        feat = _feat_cols(df)
        n_est = args.n_estimators
        es    = args.early_stopping

        # ── D: regression (RMSE) ────────────────────────────────────
        result_d = _run_one(
            "D: Overlay回帰（RMSE）",
            df_train, df_val, feat, n_est, es, "regression",
        )

        # ── E: huber（外れ値頑健） ────────────────────────────────────
        result_e = _run_one(
            "E: Overlay回帰（Huber）",
            df_train, df_val, feat, n_est, es, "huber", alpha=0.9,
        )

        results = [result_d, result_e]

        # ── 成果物保存 ────────────────────────────────────────────────
        for r in results:
            safe = (r["label"].replace(":", "").replace("（", "_")
                    .replace("）", "").replace(" ", ""))
            r["overlay_df"].to_csv(
                _OUT_DIR / f"overlay_thresh_{safe}.csv", index=False, encoding="utf-8-sig"
            )
            r["baseline_df"].to_csv(
                _OUT_DIR / f"baseline_{safe}.csv", index=False, encoding="utf-8-sig"
            )
            r["bets_df_top"].to_csv(
                _OUT_DIR / f"bets_top_{safe}.csv", index=False, encoding="utf-8-sig"
            )
            if not r["bets_df_pos"].empty:
                r["bets_df_pos"].to_csv(
                    _OUT_DIR / f"bets_pos_{safe}.csv", index=False, encoding="utf-8-sig"
                )
            r["fi"].to_csv(
                _OUT_DIR / f"fi_{safe}.csv", header=["importance"], encoding="utf-8-sig"
            )
            r["model"].booster_.save_model(
                str(_ARTIFACTS_DIR / f"lgbm_{safe}_v1.txt")
            )

        _generate_report(results, f"{val_from}〜", _OUT_DIR)

        ctx["records_processed"] = len(df_train) + len(df_val)

    print(f"\n{'='*70}")
    print("Overlay 直接ターゲット学習 - 完了")
    print(f"{'='*70}")
    print(f"  訓練: {len(df_train):,}行 / {df_train['race_id'].nunique():,}レース")
    print(f"  検証: {len(df_val):,}行 / {df_val['race_id'].nunique():,}レース")
    print()
    print(f"  {'モデル':<35} {'best_iter':>9} {'RMSE':>8} {'ROI(top)':>10} {'p値':>8}")
    print(f"  {'-'*72}")
    for r in results:
        print(
            f"  {r['label']:<35} {r['best_iter']:>9} "
            f"{r['rmse']:>8.4f} {r['roi_top']*100:>9.2f}% {r['p_value_top']:>8.4f}"
        )
    print()
    mkt_pct = round(results[0]["market_roi"] * 100, 2)
    print(f"  Market ROI: {mkt_pct:.2f}%")
    print(f"  レポート: {_OUT_DIR}/overlay_report.md")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

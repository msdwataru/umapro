"""
Binary Classification による学習方法見直し。

rank_xendcg の問題点:
  - ランキング順序を最適化するが確率推定はしない
  - EV = P(win) × odds が計算できない（ECE=0.229 の原因）

Binary Classification の利点:
  - binary 目的関数 → logloss 最小化 → 自然に calibrated な P(win) を出力
  - softmax 正規化でレース内合計 100% → Overlay = P(win) - market_prob が計算可能
  - EV = P(win)_normalized × odds で真の期待値を評価できる

3パターンを比較:
  A: binary + 全特徴量 (odds含む)
  B: binary + odds除外
  C: binary + 全特徴量 + log(odds) 重み付け (高配当的中を重視)

Usage:
    cd apps/batch
    python -m uma.models.train_binary
    python -m uma.models.train_binary --val-from 20260115 --n-estimators 500
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, brier_score_loss

from uma.db.client import get_client
from uma.jobs.base import job_context
from uma.phase0.metrics_lib import roi_ci, roi_significance, format_roi_row, drawdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"
_PARQUET_PATH  = _ARTIFACTS_DIR / "race_features_v1.parquet"
_OUT_DIR       = _ARTIFACTS_DIR / "binary_eval"

STAKE = 100.0

_BASE_EXCLUDE = {
    "race_entry_id", "race_id", "race_date",
    "finish_position", "finish_time_sec",
    "jockey_affiliation_enc",
}
_ODDS_COLS = {"latest_win_odds", "odds_inv", "odds_rank"}
_CAT_COLS  = ["sire_name", "dam_name"]

_BINARY_PARAMS = dict(
    objective         = "binary",
    metric            = "binary_logloss",
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
    # race_entry_id は着順採番のためソートキー不適切。horse_number（抽選）を使う
    df = df.sort_values(["race_date", "race_id", "horse_number"]).reset_index(drop=True)
    logger.info("Loaded: %d rows × %d cols", len(df), len(df.columns))
    return df


def _encode_cat(df: pd.DataFrame) -> pd.DataFrame:
    for col in _CAT_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


def _feat_cols(df: pd.DataFrame, include_odds: bool) -> list[str]:
    exclude = _BASE_EXCLUDE | (set() if include_odds else _ODDS_COLS)
    return [c for c in df.columns if c not in exclude]


def _make_target(df: pd.DataFrame) -> np.ndarray:
    return (df["finish_position"] == 1).astype(int).values


def _log_odds_weight(df: pd.DataFrame) -> np.ndarray:
    """高配当馬の的中を重視する sample_weight。外れ馬は 1.0 固定。"""
    w = np.ones(len(df))
    win_mask = df["finish_position"] == 1
    w[win_mask] = np.log1p(df.loc[win_mask, "latest_win_odds"].values)
    return w


# ──────────────────────────────────────────────────────────────────────
# softmax 正規化確率
# ──────────────────────────────────────────────────────────────────────

def _race_normalize(df: pd.DataFrame, raw_proba: np.ndarray) -> np.ndarray:
    """
    binary モデルの P(win) をレース内合計 1.0 に正規化する。
    - softmax ではなく単純正規化（sum normalization）を使う
      → binary の出力は既に [0,1] の確率空間にあるため
    - レース内合計がゼロの場合は均等分配
    """
    normalized = np.zeros(len(df))
    for _, grp in df.groupby("race_id", sort=False):
        idx = grp.index.values
        p   = raw_proba[idx]
        s   = p.sum()
        normalized[idx] = p / s if s > 1e-10 else np.ones(len(idx)) / len(idx)
    return normalized


# ──────────────────────────────────────────────────────────────────────
# 評価: キャリブレーション
# ──────────────────────────────────────────────────────────────────────

def _calibration(df: pd.DataFrame, proba: np.ndarray) -> tuple[pd.DataFrame, float]:
    """
    正規化前の raw P(win) でキャリブレーションを評価する。
    (正規化後はレース頭数依存になるため raw が適切)
    """
    df = df.copy()
    df["_p"] = proba
    y_true = _make_target(df)

    ece_bins = list(range(0, 105, 5))
    labels   = [f"{b}%〜{b+5}%" for b in ece_bins[:-1]]
    df["_bin"] = pd.cut(df["_p"] * 100, bins=ece_bins, labels=labels, right=False)

    rows = []
    for label, grp in df.groupby("_bin", observed=True, sort=True):
        n      = len(grp)
        actual = (grp["finish_position"] == 1).mean()
        pred   = grp["_p"].mean()
        rows.append({"bin": str(label), "n": n,
                     "pred_prob": round(float(pred), 4),
                     "actual_win": round(float(actual), 4),
                     "error": round(abs(float(actual) - float(pred)), 4)})

    cal_df = pd.DataFrame(rows)
    total  = cal_df["n"].sum()
    ece    = float((cal_df["n"] / total * cal_df["error"]).sum()) if total > 0 else np.nan

    logloss = log_loss(y_true, proba)
    brier   = brier_score_loss(y_true, proba)
    return cal_df, ece, logloss, brier


# ──────────────────────────────────────────────────────────────────────
# 評価: ROI・Overlay
# ──────────────────────────────────────────────────────────────────────

def _eval_roi_overlay(df: pd.DataFrame, norm_proba: np.ndarray) -> dict:
    """
    正規化済み P(win) から ROI と Overlay を計算する。
    Overlay = norm_prob - market_prob  (正規化済み市場確率との差)
    """
    df = df.copy()
    df["_norm_p"] = norm_proba
    df["_mkt_p"]  = df.groupby("race_id")["odds_inv"].transform(lambda x: x / x.sum())
    df["_overlay"] = df["_norm_p"] - df["_mkt_p"]

    bets = []
    for _, grp in df.groupby("race_id", sort=False):
        top_idx = grp["_norm_p"].idxmax()
        chosen  = grp.loc[top_idx]
        won     = chosen["finish_position"] == 1
        bets.append({
            "race_id":    chosen["race_id"],
            "odds_rank":  chosen["odds_rank"],
            "odds":       chosen["latest_win_odds"],
            "norm_prob":  chosen["_norm_p"],
            "market_prob":chosen["_mkt_p"],
            "overlay":    chosen["_overlay"],
            "is_win":     won,
            "payout":     chosen["latest_win_odds"] * STAKE if won else 0.0,
            "profit":     chosen["latest_win_odds"] * STAKE - STAKE if won else -STAKE,
        })

    bets_df  = pd.DataFrame(bets)
    profits  = bets_df["profit"].values
    stakes   = np.full(len(bets_df), STAKE)
    race_ids = bets_df["race_id"].values

    result  = roi_ci(profits, stakes, race_ids=race_ids)
    p_value = roi_significance(profits, stakes, race_ids=race_ids)
    result["bets_df"] = bets_df
    result["p_value"] = p_value
    return result


# ──────────────────────────────────────────────────────────────────────
# 評価: Overlay フィルター別 ROI
# ──────────────────────────────────────────────────────────────────────

def _overlay_filter_roi(bets_df: pd.DataFrame) -> pd.DataFrame:
    """Overlay しきい値別の ROI を集計する。"""
    thresholds = [0.0, 0.02, 0.05, 0.10, 0.15]
    rows = []
    for thr in thresholds:
        filtered = bets_df[bets_df["overlay"] >= thr]
        n = len(filtered)
        if n < 10:
            continue
        profits  = filtered["profit"].values
        stakes   = np.full(n, STAKE)
        race_ids = filtered["race_id"].values
        r = roi_ci(profits, stakes, race_ids=race_ids)
        p = roi_significance(profits, stakes, race_ids=race_ids)
        rows.append({
            "overlay_threshold": thr,
            "n_bets":   n,
            "hit_rate": round(filtered["is_win"].mean(), 4),
            "roi_pct":  round(r["roi"] * 100, 2),
            "ci_low":   round(r["ci_low"] * 100, 2),
            "ci_high":  round(r["ci_high"] * 100, 2),
            "p_value":  round(p, 4),
            "significant": p < 0.05,
        })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────
# ベースライン比較（軽量版・Monte Carlo なし）
# ──────────────────────────────────────────────────────────────────────

def _baseline_comparison(df: pd.DataFrame, norm_proba: np.ndarray, label: str) -> pd.DataFrame:
    rows = []

    # Favorite
    favs = df[df["odds_rank"] == 1]
    fav_won = favs["finish_position"] == 1
    fav_p   = np.where(fav_won, favs["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_fav   = roi_ci(fav_p, np.full(len(favs), STAKE), race_ids=favs["race_id"].values)
    p_fav   = roi_significance(fav_p, np.full(len(favs), STAKE), race_ids=favs["race_id"].values)
    rows.append(format_roi_row("Favorite（1番人気）", r_fav, p_value=p_fav))

    # Market
    df2 = df.copy()
    df2["_oi"] = 1.0 / df2["latest_win_odds"]
    df2["_mp"] = df2.groupby("race_id")["_oi"].transform(lambda x: x / x.sum())
    mkt_idx = df2.groupby("race_id")["_mp"].idxmax()
    mkt     = df2.loc[mkt_idx]
    mkt_won = mkt["finish_position"] == 1
    mkt_p   = np.where(mkt_won, mkt["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_mkt   = roi_ci(mkt_p, np.full(len(mkt), STAKE), race_ids=mkt["race_id"].values)
    p_mkt   = roi_significance(mkt_p, np.full(len(mkt), STAKE), race_ids=mkt["race_id"].values)
    market_roi = r_mkt["roi"]
    rows.append(format_roi_row("Market（市場確率最大）★天井", r_mkt, p_value=p_mkt))

    # Model
    df3 = df.copy()
    df3["_norm_p"] = norm_proba
    model_idx = df3.groupby("race_id")["_norm_p"].idxmax()
    model_ch  = df3.loc[model_idx]
    m_won     = model_ch["finish_position"] == 1
    m_profits = np.where(m_won, model_ch["latest_win_odds"] * STAKE - STAKE, -STAKE)
    r_model   = roi_ci(m_profits, np.full(len(model_ch), STAKE), race_ids=model_ch["race_id"].values)
    p_model   = roi_significance(m_profits, np.full(len(model_ch), STAKE),
                                 race_ids=model_ch["race_id"].values, null_roi=market_roi)
    rows.append(format_roi_row(label, r_model, p_value=p_model, reference_roi=market_roi))

    return pd.DataFrame(rows)


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
    sample_weight: np.ndarray | None = None,
) -> dict:
    logger.info("=== %s ===", label)
    logger.info("features=%d  train=%d  val=%d", len(feat_cols), len(df_train), len(df_val))

    X_train = df_train[feat_cols]
    y_train = _make_target(df_train)
    X_val   = df_val[feat_cols]
    y_val   = _make_target(df_val)

    model = lgb.LGBMClassifier(**{**_BINARY_PARAMS, "n_estimators": n_estimators})
    callbacks = [lgb.log_evaluation(50)]
    if early_stopping > 0:
        callbacks.append(lgb.early_stopping(early_stopping, verbose=True))

    fit_kwargs: dict = {
        "eval_set":            [(X_val, y_val)],
        "categorical_feature": [c for c in _CAT_COLS if c in feat_cols],
        "callbacks":           callbacks,
    }
    if sample_weight is not None:
        fit_kwargs["sample_weight"] = sample_weight

    model.fit(X_train, y_train, **fit_kwargs)
    best_iter = model.best_iteration_ or n_estimators
    logger.info("%s best_iteration=%d", label, best_iter)

    # 予測（raw P(win)）
    raw_proba = model.predict_proba(X_val)[:, 1]

    # レース内正規化
    norm_proba = _race_normalize(df_val, raw_proba)

    # キャリブレーション
    cal_df, ece, logloss, brier = _calibration(df_val, raw_proba)
    logger.info("%s ECE=%.4f  LogLoss=%.4f  Brier=%.4f", label, ece, logloss, brier)

    # ROI・Overlay
    roi_result = _eval_roi_overlay(df_val, norm_proba)
    logger.info(
        "%s ROI=%.2f%%  CI=[%.2f%%, %.2f%%]  p=%.4f",
        label,
        roi_result["roi"] * 100,
        roi_result["ci_low"] * 100,
        roi_result["ci_high"] * 100,
        roi_result["p_value"],
    )

    # Overlay フィルター
    overlay_df = _overlay_filter_roi(roi_result["bets_df"])

    # ベースライン比較
    baseline_df = _baseline_comparison(df_val, norm_proba, label)

    # 特徴量重要度
    fi = pd.Series(model.feature_importances_, index=feat_cols).sort_values(ascending=False)

    return {
        "label":        label,
        "best_iter":    best_iter,
        "ece":          ece,
        "logloss":      logloss,
        "brier":        brier,
        "roi":          roi_result["roi"],
        "ci_low":       roi_result["ci_low"],
        "ci_high":      roi_result["ci_high"],
        "p_value":      roi_result["p_value"],
        "n_bets":       roi_result["n_bets"],
        "cal_df":       cal_df,
        "overlay_df":   overlay_df,
        "baseline_df":  baseline_df,
        "bets_df":      roi_result["bets_df"],
        "fi":           fi,
        "model":        model,
    }


# ──────────────────────────────────────────────────────────────────────
# レポート生成
# ──────────────────────────────────────────────────────────────────────

def _generate_report(results: list[dict], val_period: str, out_dir: Path) -> None:
    lines = [
        "# Binary Classification 学習方法見直し — 評価レポート",
        "",
        f"**評価期間**: {val_period}（Walk-Forward Fold5 out-of-sample）",
        "> ⚠️ OPTIMISTIC_BIAS: ROI は確定オッズ近似値による楽観値。",
        "",
        "---",
        "",
        "## サマリー比較",
        "",
        "| モデル | best_iter | ECE | LogLoss | ROI | 95% CI | p値 | Market超過 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    # Market ROI を baseline_df から取得
    market_roi_pct = None
    for r in results:
        for row in r["baseline_df"].to_dict("records"):
            if "Market" in str(row.get("label", "")):
                market_roi_pct = row.get("roi_pct")
                break
        if market_roi_pct:
            break

    for r in results:
        roi_pct = round(r["roi"] * 100, 2)
        vs_mkt  = (f"{roi_pct - market_roi_pct:+.2f}pt"
                   if market_roi_pct is not None else "-")
        sig     = "✅" if r["p_value"] < 0.05 else "❌"
        lines.append(
            f"| {r['label']} | {r['best_iter']} "
            f"| {r['ece']:.4f} | {r['logloss']:.4f} "
            f"| {roi_pct}% | [{r['ci_low']*100:.2f}%, {r['ci_high']*100:.2f}%] "
            f"| {r['p_value']:.4f} | {sig} {vs_mkt} |"
        )

    lines += ["", "---", ""]

    for r in results:
        lines += [f"## {r['label']}", ""]

        # Overlay フィルター
        lines += ["### Overlay フィルター別 ROI", ""]
        lines += ["| Overlay ≥ | 購入数 | 的中率 | ROI | 95% CI | p値 | 有意 |",
                  "|---|---|---|---|---|---|---|"]
        for _, row in r["overlay_df"].iterrows():
            sig = "✅" if row["significant"] else "❌"
            lines.append(
                f"| {row['overlay_threshold']:.0%} | {row['n_bets']} "
                f"| {row['hit_rate']:.3f} | {row['roi_pct']}% "
                f"| [{row['ci_low']}%, {row['ci_high']}%] "
                f"| {row['p_value']:.4f} | {sig} |"
            )

        # キャリブレーション
        lines += ["", "### キャリブレーション（raw P(win)）", "",
                  f"**ECE**: {r['ece']:.4f}  **LogLoss**: {r['logloss']:.4f}  **Brier**: {r['brier']:.4f}",
                  "",
                  "| 予測確率帯 | 件数 | 予測確率 | 実勝率 | 誤差 |",
                  "|---|---|---|---|---|"]
        for _, row in r["cal_df"].iterrows():
            if row["n"] >= 10:
                lines.append(
                    f"| {row['bin']} | {row['n']} "
                    f"| {row['pred_prob']:.4f} | {row['actual_win']:.4f} "
                    f"| {row['error']:.4f} |"
                )

        # ベースライン比較
        lines += ["", "### ベースライン比較", "",
                  "| Strategy | 購入数 | ROI | 95% CI | p値 | 有意 | Marketとの差 |",
                  "|---|---|---|---|---|---|---|"]
        for _, row in r["baseline_df"].iterrows():
            sig = "✅" if row.get("significant") else "❌"
            vs  = (f"{row.get('vs_reference_pt', '-'):+.2f}pt"
                   if row.get("vs_reference_pt") is not None else "-")
            lines.append(
                f"| {row.get('label','')} | {row.get('n_bets',0)} "
                f"| {row.get('roi_pct','N/A')}% "
                f"| [{row.get('ci_low_pct','?')}%, {row.get('ci_high_pct','?')}%] "
                f"| {row.get('p_value', '-')} | {sig} | {vs} |"
            )

        # 特徴量重要度 Top10
        lines += ["", "### 特徴量重要度 Top10", "",
                  "| Rank | 特徴量 | Importance |", "|---|---|---|"]
        for i, (name, val) in enumerate(r["fi"].head(10).items(), 1):
            lines.append(f"| {i} | {name} | {val:.0f} |")

        lines += ["", "---", ""]

    report_path = out_dir / "binary_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("レポート保存: %s", report_path)


# ──────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Binary Classification 学習方法見直し")
    parser.add_argument("--val-from", default="20260115", metavar="YYYYMMDD")
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--early-stopping", type=int, default=50)
    parser.add_argument("--parquet", default=str(_PARQUET_PATH))
    args = parser.parse_args()

    val_from = datetime.strptime(args.val_from, "%Y%m%d").strftime("%Y-%m-%d")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = get_client()

    with job_context("train_binary_classifier", "train") as ctx:
        df = _load(Path(args.parquet))
        df = _encode_cat(df)

        train_mask = df["race_date"] < val_from
        val_mask   = df["race_date"] >= val_from
        df_train   = df[train_mask].reset_index(drop=True)
        df_val     = df[val_mask].reset_index(drop=True)

        logger.info(
            "分割: train=%d行/%dレース  val=%d行/%dレース",
            len(df_train), df_train["race_id"].nunique(),
            len(df_val),   df_val["race_id"].nunique(),
        )

        n_est = args.n_estimators
        es    = args.early_stopping

        # ── パターン A: binary + 全特徴量（odds 含む） ──────────────
        feat_a = _feat_cols(df, include_odds=True)
        result_a = _run_one("A: binary（odds含む）", df_train, df_val, feat_a, n_est, es)

        # ── パターン B: binary + odds 除外 ─────────────────────────
        feat_b = _feat_cols(df, include_odds=False)
        result_b = _run_one("B: binary（odds除外）", df_train, df_val, feat_b, n_est, es)

        # ── パターン C: binary + 全特徴量 + log(odds) 重み付け ──────
        weights_c = _log_odds_weight(df_train)
        result_c = _run_one("C: binary（odds含む + log重み）",
                             df_train, df_val, feat_a, n_est, es, sample_weight=weights_c)

        results = [result_a, result_b, result_c]

        # ── 成果物保存 ────────────────────────────────────────────────
        for r in results:
            safe_label = r["label"].replace(":", "").replace("（", "_").replace("）", "").replace(" ", "")
            r["cal_df"].to_csv(
                _OUT_DIR / f"calibration_{safe_label}.csv", index=False, encoding="utf-8-sig"
            )
            r["overlay_df"].to_csv(
                _OUT_DIR / f"overlay_{safe_label}.csv", index=False, encoding="utf-8-sig"
            )
            r["baseline_df"].to_csv(
                _OUT_DIR / f"baseline_{safe_label}.csv", index=False, encoding="utf-8-sig"
            )
            r["bets_df"].to_csv(
                _OUT_DIR / f"bets_{safe_label}.csv", index=False, encoding="utf-8-sig"
            )
            r["fi"].to_csv(
                _OUT_DIR / f"fi_{safe_label}.csv", header=["importance"], encoding="utf-8-sig"
            )
            r["model"].booster_.save_model(
                str(_ARTIFACTS_DIR / f"lgbm_{safe_label}_v1.txt")
            )

        # ── レポート ──────────────────────────────────────────────────
        _generate_report(results, f"{val_from}〜", _OUT_DIR)

        ctx["records_processed"] = len(df_train) + len(df_val)

    # ── コンソール出力 ─────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("Binary Classification 学習方法見直し - 完了")
    print(f"{'='*65}")
    print(f"  訓練: {len(df_train):,}行 / {df_train['race_id'].nunique():,}レース")
    print(f"  検証: {len(df_val):,}行 / {df_val['race_id'].nunique():,}レース")
    print()
    print(f"  {'モデル':<30} {'best_iter':>9} {'ECE':>8} {'ROI':>9} {'p値':>8}")
    print(f"  {'-'*65}")
    for r in results:
        print(
            f"  {r['label']:<30} {r['best_iter']:>9} "
            f"{r['ece']:>8.4f} {r['roi']*100:>8.2f}% {r['p_value']:>8.4f}"
        )
    print()
    print(f"  レポート: {_OUT_DIR}/binary_report.md")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()

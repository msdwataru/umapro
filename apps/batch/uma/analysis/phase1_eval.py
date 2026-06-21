"""
Phase 1 評価スクリプト — モデルの実力を5軸で分析する。

Usage:
    cd apps/batch
    python -m uma.analysis.phase1_eval --run-id 22
    python -m uma.analysis.phase1_eval --run-id 22 --run-id 19
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uma.db.client import get_client, paginate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"
PARQUET_PATH  = ARTIFACTS_DIR / "race_features_v1.parquet"
OUTPUT_DIR    = ARTIFACTS_DIR / "phase1_eval"
STAKE         = 100  # 1 bet あたり賭け金（円）


# ── ユーティリティ ────────────────────────────────────────────────────

def _md_table(df: pd.DataFrame) -> str:
    """pandas DataFrame を GitHub Flavored Markdown テーブルに変換する。"""
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep    = "| " + " | ".join("---" for _ in cols) + " |"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append(f"{v:.4f}" if not np.isnan(v) else "N/A")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def _roi_str(v: float) -> str:
    return "N/A" if np.isnan(v) else f"{v * 100:.1f}%"


# ── データロード ──────────────────────────────────────────────────────

def load_parquet() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET_PATH)
    return df[df["finish_position"].notna()].copy()


def load_bets_df(client, run_id: int, parquet_df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Loading backtest_bets for run_id=%d", run_id)
    rows = paginate(lambda off, lim:
        client.table("backtest_bets")
        .select("race_id,race_entry_id,is_hit,payout_amount,stake_amount,prediction_value,edge_value")
        .eq("backtest_run_id", run_id)
        .range(off, off + lim - 1)
    )
    if not rows:
        raise ValueError(f"run_id={run_id} に bets がありません")

    df = pd.DataFrame(rows)
    for col in ["prediction_value", "edge_value", "payout_amount", "stake_amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["is_hit"]  = df["is_hit"].astype(bool)
    df["race_id"] = df["race_id"].astype(int)

    # implied_probability = prediction_value - edge_value
    df["implied_probability"] = df["prediction_value"] - df["edge_value"]
    # EV = predicted / implied（0 除算を回避）
    df["ev"] = df["prediction_value"] / df["implied_probability"].clip(lower=1e-6)

    # parquet から odds_rank, latest_win_odds を結合
    pq_sub = (
        parquet_df[["race_entry_id", "odds_rank", "latest_win_odds"]]
        .drop_duplicates("race_entry_id")
    )
    df = df.merge(pq_sub, on="race_entry_id", how="left")

    match_rate = df["odds_rank"].notna().mean() * 100
    logger.info("  bets=%d  parquet match=%.1f%%", len(df), match_rate)
    return df


# ── Task 1: 人気別 ROI ────────────────────────────────────────────────

def task1_popularity_roi(bets_df: pd.DataFrame) -> pd.DataFrame:
    df = bets_df.dropna(subset=["odds_rank"]).copy()
    df["pop"] = df["odds_rank"].clip(upper=18).astype(int)

    records = []
    for pop in range(1, 19):
        g = df[df["pop"] == pop]
        if g.empty:
            continue
        n   = len(g)
        hit = int(g["is_hit"].sum())
        st  = g["stake_amount"].sum()
        pay = g["payout_amount"].sum()
        roi = (pay - st) / st if st > 0 else float("nan")
        records.append({
            "人気": pop,
            "購入数": n,
            "的中数": hit,
            "的中率": round(hit / n, 4),
            "ROI": round(roi, 4),
        })
    return pd.DataFrame(records)


# ── Task 2: オッズ帯別 ROI ────────────────────────────────────────────

_ODDS_BINS   = [1, 2, 3, 5, 10, 20, 50, 9999]
_ODDS_LABELS = ["1〜2", "2〜3", "3〜5", "5〜10", "10〜20", "20〜50", "50以上"]

def task2_odds_roi(bets_df: pd.DataFrame) -> pd.DataFrame:
    df = bets_df.dropna(subset=["latest_win_odds"]).copy()
    df["帯"] = pd.cut(df["latest_win_odds"], bins=_ODDS_BINS, labels=_ODDS_LABELS, right=False)

    records = []
    for lbl in _ODDS_LABELS:
        g = df[df["帯"] == lbl]
        if g.empty:
            continue
        n   = len(g)
        hit = g["is_hit"].sum()
        st  = g["stake_amount"].sum()
        pay = g["payout_amount"].sum()
        roi = (pay - st) / st if st > 0 else float("nan")
        records.append({
            "オッズ帯": lbl,
            "購入数": n,
            "的中率": round(hit / n, 4),
            "ROI": round(roi, 4),
        })
    return pd.DataFrame(records)


# ── Task 3: Calibration Analysis ─────────────────────────────────────

def task3_calibration(
    bets_df: pd.DataFrame,
    run_label: str,
) -> tuple[pd.DataFrame, dict]:
    df = bets_df.copy()
    bins = np.arange(0, 0.55, 0.05)   # 0〜50% の範囲（競馬の予測確率帯）
    df["bin"] = pd.cut(df["prediction_value"], bins=bins, right=False)

    records = []
    for b, g in df.groupby("bin", observed=True):
        mid = round(float((b.left + b.right) / 2), 4)
        win_rate = float(g["is_hit"].mean()) if len(g) > 0 else float("nan")
        records.append({
            "予測確率帯": f"{b.left:.0%}〜{b.right:.0%}",
            "件数": len(g),
            "予測確率中央値": mid,
            "実勝率": round(win_rate, 4) if not np.isnan(win_rate) else float("nan"),
        })
    cal_df = pd.DataFrame(records)

    # ECE
    total_n = len(df)
    ece = 0.0
    max_err = 0.0
    for _, row in cal_df.iterrows():
        if row["件数"] == 0 or np.isnan(row["実勝率"]):
            continue
        err = abs(row["実勝率"] - row["予測確率中央値"])
        ece += (row["件数"] / total_n) * err
        max_err = max(max_err, err)
    metrics = {
        "ECE": round(ece, 4),
        "max_bin_error": round(max_err, 4),
        "n_samples": total_n,
    }

    # プロット
    valid = cal_df[(cal_df["件数"] >= 5) & cal_df["実勝率"].notna()]
    fig, ax = plt.subplots(figsize=(7, 7))
    sizes = (valid["件数"] / valid["件数"].max() * 300 + 30).values
    ax.scatter(valid["予測確率中央値"], valid["実勝率"], s=sizes, alpha=0.7, zorder=3,
               label="実測値（円の大きさ = 件数）")
    lim = max(cal_df["予測確率中央値"].max(), cal_df["実勝率"].max()) * 1.1
    ax.plot([0, lim], [0, lim], "k--", alpha=0.4, label="Perfect calibration")
    ax.set_xlabel("予測確率（モデル）")
    ax.set_ylabel("実勝率")
    ax.set_title(f"Calibration Curve — {run_label[:40]}\nECE={ece:.4f}")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "calibration_curve.png", dpi=150)
    plt.close(fig)
    logger.info("calibration_curve.png saved  ECE=%.4f", ece)

    return cal_df, metrics


# ── Task 4: EV フィルター検証 ────────────────────────────────────────

_EV_BINS   = [0, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5, 99]
_EV_LABELS = ["〜0.8", "0.8〜0.9", "0.9〜1.0", "1.0〜1.1", "1.1〜1.2", "1.2〜1.5", "1.5〜"]

def task4_ev_analysis(bets_df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    df = bets_df.dropna(subset=["ev"]).copy()
    df["EV帯"] = pd.cut(df["ev"], bins=_EV_BINS, labels=_EV_LABELS, right=False)

    records = []
    for lbl in _EV_LABELS:
        g = df[df["EV帯"] == lbl]
        if g.empty:
            continue
        n   = len(g)
        hit = g["is_hit"].sum()
        st  = g["stake_amount"].sum()
        pay = g["payout_amount"].sum()
        roi = (pay - st) / st if st > 0 else float("nan")
        records.append({
            "EV帯": lbl,
            "購入数": n,
            "的中率": round(hit / n, 4),
            "ROI": round(roi, 4),
        })
    ev_df = pd.DataFrame(records)

    # EV と実現 ROI（1 bet あたり損益率）の相関
    df["bet_roi"] = df["payout_amount"] / df["stake_amount"] - 1
    corr = float(df["ev"].corr(df["bet_roi"]))
    logger.info("EV-ROI correlation: %.4f", corr)
    return ev_df, round(corr, 4)


# ── Task 5: ベースライン比較 ─────────────────────────────────────────

def task5_baseline(
    bets_df: pd.DataFrame,
    parquet_df: pd.DataFrame,
    run_label: str,
) -> pd.DataFrame:
    race_ids  = set(bets_df["race_id"].dropna().astype(int))
    df_races  = parquet_df[parquet_df["race_id"].isin(race_ids)].copy()
    n_races   = len(race_ids)

    def roi_from(payout_arr, n_bets: int) -> float:
        total_stake  = n_bets * STAKE
        total_payout = float(np.sum(payout_arr))
        return (total_payout - total_stake) / total_stake if total_stake > 0 else float("nan")

    records = []

    # Random（モンテカルロ 100 回）
    rng = np.random.default_rng(42)
    random_rois, random_hits = [], []
    for _ in range(100):
        payouts, hits = [], []
        for _, grp in df_races.groupby("race_id", sort=False):
            if grp.empty:
                continue
            idx = rng.integers(len(grp))
            row = grp.iloc[idx]
            win  = row["finish_position"] == 1
            pay  = float(row["latest_win_odds"]) * STAKE if win else 0.0
            payouts.append(pay)
            hits.append(int(win))
        random_rois.append(roi_from(payouts, len(payouts)))
        random_hits.append(np.mean(hits))
    records.append({
        "Strategy": "Random",
        "購入数": n_races,
        "的中率": round(float(np.mean(random_hits)), 4),
        "ROI": round(float(np.mean(random_rois)), 4),
    })

    # Favorite（odds_rank=1）
    df_fav = df_races[df_races["odds_rank"] == 1].copy()
    if not df_fav.empty:
        df_fav["win"] = df_fav["finish_position"] == 1
        df_fav["pay"] = df_fav.apply(
            lambda r: float(r["latest_win_odds"]) * STAKE if r["win"] else 0.0, axis=1
        )
        records.append({
            "Strategy": "Favorite（1番人気）",
            "購入数": len(df_fav),
            "的中率": round(float(df_fav["win"].mean()), 4),
            "ROI": round(roi_from(df_fav["pay"].values, len(df_fav)), 4),
        })

    # 指定モデル
    model_roi = (
        (bets_df["payout_amount"].sum() - bets_df["stake_amount"].sum())
        / bets_df["stake_amount"].sum()
    )
    records.append({
        "Strategy": run_label[:40],
        "購入数": len(bets_df),
        "的中率": round(float(bets_df["is_hit"].mean()), 4),
        "ROI": round(float(model_roi), 4),
    })

    return pd.DataFrame(records)


# ── レポート生成 ──────────────────────────────────────────────────────

def generate_report(
    run_labels: list[str],
    pop_results: dict,
    odds_results: dict,
    cal_results: dict,
    ev_results: dict,
    baseline_results: dict,
) -> None:
    lines: list[str] = [
        "# Phase 1 評価レポート",
        "",
        f"**分析対象モデル**: {', '.join(run_labels)}",
        "",
        "---",
        "",
    ]

    # Task 1
    lines.append("## Task 1: 人気別 ROI")
    for label, df in pop_results.items():
        lines += ["", f"### {label}", "", _md_table(df)]

    # Task 2
    lines.append("\n## Task 2: オッズ帯別 ROI")
    for label, df in odds_results.items():
        lines += ["", f"### {label}", "", _md_table(df)]

    # Task 3
    lines.append("\n## Task 3: Calibration Analysis")
    lines.append("\n![Calibration Curve](calibration_curve.png)")
    for label, (cal_df, metrics) in cal_results.items():
        lines += [
            "",
            f"### {label}",
            "",
            _md_table(cal_df),
            "",
            f"**ECE**: {metrics['ECE']}  |  **最大誤差**: {metrics['max_bin_error']}  |  **件数**: {metrics['n_samples']}",
        ]

    # Task 4
    lines.append("\n## Task 4: EV フィルター検証")
    for label, (ev_df, corr) in ev_results.items():
        lines += [
            "",
            f"### {label}",
            "",
            _md_table(ev_df),
            "",
            f"**EV と ROI の相関係数**: {corr}",
            f"({'EV が機能している' if corr > 0.05 else 'EV と ROI に相関なし — 確率推定の見直しが必要'})",
        ]

    # Task 5
    lines.append("\n## Task 5: ベースライン比較")
    any_above = False
    for label, df in baseline_results.items():
        lines += ["", f"### {label}", "", _md_table(df)]

        fav_rows   = df[df["Strategy"].str.contains("Favorite")]
        model_rows = df[~df["Strategy"].str.contains("Favorite|Random")]
        if not fav_rows.empty and not model_rows.empty:
            fav_roi   = float(fav_rows["ROI"].iloc[0])
            model_roi = float(model_rows["ROI"].iloc[-1])
            diff      = model_roi - fav_roi
            if diff > 0.05:
                verdict = f"✅ 理想クリア (model > Favorite +5%): {diff * 100:.1f}pt 優位"
                any_above = True
            elif diff > 0.03:
                verdict = f"🟡 推奨クリア (model > Favorite +3%): {diff * 100:.1f}pt 優位"
                any_above = True
            elif diff > 0:
                verdict = f"🟠 最低条件クリア (model > Favorite): {diff * 100:.1f}pt 優位"
                any_above = True
            else:
                verdict = f"❌ 最低条件未達 (model <= Favorite): {diff * 100:.1f}pt 劣位"
            lines += ["", f"**成功基準判定**: {verdict}"]

    # Phase1 総合判定
    lines += [
        "",
        "---",
        "",
        "## Phase 1 総合判定",
    ]
    if any_above:
        lines += [
            "",
            "### 判定: **A — モデルに優位性あり**",
            "",
            "→ **Feature Engineering フェーズへ進む**",
        ]
    else:
        lines += [
            "",
            "### 判定: **B — モデルに優位性なし**",
            "",
            "→ **学習方法の見直しを優先する**",
            "",
            "- Ranker 化の再検討",
            "- Target 変更",
            "- データ品質改善",
        ]

    (OUTPUT_DIR / "phase1_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    logger.info("phase1_report.md saved")


# ── メイン ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 評価スクリプト")
    parser.add_argument("--run-id", type=int, action="append", required=True, dest="run_ids",
                        help="分析する backtest_run_id（複数指定可）")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client     = get_client()
    parquet_df = load_parquet()
    logger.info("Parquet loaded: %d rows", len(parquet_df))

    run_info     = client.table("backtest_runs").select("id,run_name").in_("id", args.run_ids).execute().data
    label_map    = {r["id"]: r["run_name"] for r in run_info}

    pop_results      : dict = {}
    odds_results     : dict = {}
    cal_results      : dict = {}
    ev_results       : dict = {}
    baseline_results : dict = {}

    for run_id in args.run_ids:
        label = label_map.get(run_id, f"run_{run_id}")
        logger.info("=== run %d: %s ===", run_id, label)

        bets_df = load_bets_df(client, run_id, parquet_df)

        pop_results[label]      = task1_popularity_roi(bets_df)
        odds_results[label]     = task2_odds_roi(bets_df)
        cal_results[label]      = task3_calibration(bets_df, label)
        ev_results[label]       = task4_ev_analysis(bets_df)
        baseline_results[label] = task5_baseline(bets_df, parquet_df, label)

    # ── CSV / JSON 出力 ──────────────────────────────────────────────
    slug = lambda s: s[:25].replace(" ", "_").replace("/", "-")

    for label, df in pop_results.items():
        df.to_csv(OUTPUT_DIR / f"popularity_roi_{slug(label)}.csv", index=False, encoding="utf-8-sig")
    for label, df in odds_results.items():
        df.to_csv(OUTPUT_DIR / f"odds_roi_{slug(label)}.csv", index=False, encoding="utf-8-sig")

    first_label = label_map.get(args.run_ids[0], f"run_{args.run_ids[0]}")
    (OUTPUT_DIR / "calibration_metrics.json").write_text(
        json.dumps(cal_results[first_label][1], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for label, (cal_df, _) in cal_results.items():
        cal_df.to_csv(OUTPUT_DIR / f"calibration_{slug(label)}.csv", index=False, encoding="utf-8-sig")

    for label, (ev_df, _) in ev_results.items():
        ev_df.to_csv(OUTPUT_DIR / f"ev_analysis_{slug(label)}.csv", index=False, encoding="utf-8-sig")
    for label, df in baseline_results.items():
        df.to_csv(OUTPUT_DIR / f"baseline_{slug(label)}.csv", index=False, encoding="utf-8-sig")

    generate_report(
        [label_map.get(rid, f"run_{rid}") for rid in args.run_ids],
        pop_results, odds_results, cal_results, ev_results, baseline_results,
    )

    logger.info("Phase1 完了 → %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()

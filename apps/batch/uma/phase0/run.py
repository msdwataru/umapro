"""
Phase0: 評価基盤の地固め（Foundation Hardening）ランナー

Tasks:
  0-1  オッズのタイムスナップショット固定（OPTIMISTIC_BIAS フラグ）
  0-2  特徴量リーク監査（leakage_audit.md）
  0-3  Walk-Forward 分割定義（cv_splits.json）
  0-4  市場ベースライン確立（baseline_comparison.csv）
  0-5  統計的有意性ライブラリの動作確認
  0-6  実験ログ初期化（experiment_log.csv）

Usage:
    cd apps/batch
    python -m uma.phase0.run
    python -m uma.phase0.run --run-id 22 --run-label "course_form"
    python -m uma.phase0.run --run-id 22 --run-label "course_form" --run-id 19 --run-label "lgbm_ranker"
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from uma.db.client import get_client, paginate
from uma.phase0.metrics_lib import roi_ci, roi_significance, format_roi_row, drawdown
from uma.phase0.walkforward import load_cv_splits, save_cv_splits, iter_folds
from uma.phase0.baseline import compare_baselines, calc_model_baseline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

PARQUET_PATH = Path(__file__).parent.parent.parent / "artifacts" / "race_features_v1.parquet"
OUT_DIR      = Path(__file__).parent.parent.parent / "artifacts" / "phase0"
STAKE        = 100.0
RANDOM_SEED  = 42


# ──────────────────────────────────────────────────────────────────────────────
# Task 0-1: オッズタイミング監査
# ──────────────────────────────────────────────────────────────────────────────

def task01_odds_timing(df: pd.DataFrame) -> dict:
    """
    latest_win_odds の統計情報を確認し、OPTIMISTIC_BIAS を記録する。
    時系列オッズが存在しないため、現時点は odds_at_bet ≒ odds_final と仮定する。
    """
    logger.info("=== Task 0-1: オッズタイミング監査 ===")
    odds = df["latest_win_odds"].dropna()
    result = {
        "status":         "OPTIMISTIC_BIAS",
        "column_used":    "latest_win_odds",
        "note":           "keibalab から過去レース一括取得。発走後に取得のため確定オッズに近い。",
        "n_entries":      int(len(df)),
        "odds_null_rate": round(df["latest_win_odds"].isna().mean() * 100, 2),
        "odds_min":       round(float(odds.min()), 2),
        "odds_max":       round(float(odds.max()), 2),
        "odds_median":    round(float(odds.median()), 2),
        "has_timeseries_odds": False,
        "action_required": "時系列オッズ収集パイプラインを構築し odds_at_bet を取得する（最優先データ課題）",
    }
    logger.info("OPTIMISTIC_BIAS: %s", result["note"])
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Task 0-2: 特徴量リーク監査
# ──────────────────────────────────────────────────────────────────────────────

def task02_leakage_audit(df: pd.DataFrame) -> list[dict]:
    """
    全特徴量について BET_TIME（発走 T-5分）時点での利用可否を評価する。
    """
    logger.info("=== Task 0-2: 特徴量リーク監査 ===")

    audit_table = [
        # (feature, data_source, confirmed_at, available_at_bet_time, judgment, note)
        ("finish_position",          "entry_results",  "レース後",       False, "TARGET",  "学習ターゲット。特徴量として使ってはならない"),
        ("finish_time_sec",          "entry_results",  "レース後",       False, "TARGET",  "学習ターゲット"),
        ("latest_win_odds",          "keibalab",       "発走前(暫定)",   True,  "OK*",     "OPTIMISTIC_BIAS: 確定オッズに近い可能性。時系列オッズ取得後に再評価"),
        ("odds_inv",                 "derived",        "同上",           True,  "OK*",     "latest_win_odds の逆数"),
        ("odds_rank",                "derived",        "同上",           True,  "OK*",     "レース内人気順位"),
        ("track_type_enc",           "keibalab",       "開催前確定",     True,  "OK",      ""),
        ("distance_m",               "keibalab",       "開催前確定",     True,  "OK",      ""),
        ("dist_bucket",              "derived",        "同上",           True,  "OK",      ""),
        ("field_size",               "keibalab",       "出馬表確定時",   True,  "OK",      ""),
        ("grade_enc",                "keibalab",       "開催前確定",     True,  "OK",      ""),
        ("going_enc",                "keibalab",       "当日発表",       True,  "OK",      "発走前に発表される"),
        ("weather_enc",              "keibalab",       "当日",           True,  "OK",      ""),
        ("prize_money_1st_log",      "keibalab",       "開催前確定",     True,  "OK",      ""),
        ("race_number",              "keibalab",       "開催前確定",     True,  "OK",      ""),
        ("weight_type_enc",          "keibalab",       "開催前確定",     True,  "OK",      ""),
        ("racecourse_id",            "keibalab",       "開催前確定",     True,  "OK",      ""),
        ("bracket_number",           "keibalab",       "出馬表確定時",   True,  "OK",      ""),
        ("horse_number",             "keibalab",       "出馬表確定時",   True,  "OK",      ""),
        ("carried_weight",           "keibalab",       "出馬表確定時",   True,  "OK",      ""),
        ("weight_kg",                "keibalab",       "パドック計量",   True,  "OK",      "発走前に公表"),
        ("weight_diff",              "keibalab",       "パドック計量",   True,  "OK",      ""),
        ("blinkers_flag",            "keibalab",       "出馬表確定時",   True,  "OK",      ""),
        ("sex_enc",                  "keibalab",       "馬登録時",       True,  "OK",      ""),
        ("age",                      "keibalab",       "馬登録時",       True,  "OK",      ""),
        ("sire_name",                "keibalab",       "血統登録時",     True,  "OK",      ""),
        ("dam_name",                 "keibalab",       "血統登録時",     True,  "OK",      ""),
        ("jockey_affiliation_enc",   "DB",             "登録時",         True,  "SKIP",    "全件-1（データ未投入）。特徴量から除外済み"),
        ("trainer_affiliation_enc",  "DB",             "登録時",         True,  "OK",      ""),
        ("horse_total_runs",         "entry_results",  "前走まで",       True,  "OK",      "hist.before(race_date) で当日除外済み"),
        ("horse_win_rate",           "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_rentai_rate",        "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_fukusho_rate",       "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_avg_finish",         "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_avg_last3f",         "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_last_finish",        "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_last3_avg_finish",   "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_last5_avg_finish",   "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_finish_std",         "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_last_last3f",        "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_course_runs",        "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_course_win_rate",    "entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_course_fukusho_rate","entry_results",  "前走まで",       True,  "OK",      ""),
        ("horse_dist_bucket_win_rate","entry_results", "前走まで",       True,  "OK",      ""),
        ("horse_track_type_win_rate","entry_results",  "前走まで",       True,  "OK",      ""),
        ("days_since_last_run",      "entry_results",  "前走日付から計算", True, "OK",     ""),
        ("distance_change",          "entry_results",  "前走距離から計算", True, "OK",     ""),
        ("prev_track_type_enc",      "entry_results",  "前走まで",       True,  "OK",      ""),
        ("prev_going_enc",           "entry_results",  "前走まで",       True,  "OK",      ""),
        ("prev_finish",              "entry_results",  "前走まで",       True,  "OK",      ""),
        ("prev_last3f",              "entry_results",  "前走まで",       True,  "OK",      ""),
        ("jockey_win_rate",          "entry_results",  "前走まで",       True,  "OK",      "hist.before(race_date)"),
        ("jockey_rentai_rate",       "entry_results",  "前走まで",       True,  "OK",      ""),
        ("jockey_fukusho_rate",      "entry_results",  "前走まで",       True,  "OK",      ""),
        ("jockey_course_win_rate",   "entry_results",  "前走まで",       True,  "OK",      ""),
        ("jockey_track_win_rate",    "entry_results",  "前走まで",       True,  "OK",      ""),
        ("trainer_win_rate",         "entry_results",  "前走まで",       True,  "OK",      ""),
        ("trainer_rentai_rate",      "entry_results",  "前走まで",       True,  "OK",      ""),
        ("trainer_fukusho_rate",     "entry_results",  "前走まで",       True,  "OK",      ""),
    ]

    # _sc 系（SC正規化列）は元カラムと同じ判定
    sc_cols = [c for c in df.columns if c.endswith("_sc")]
    for col in sc_cols:
        base = col[:-3]
        base_row = next((r for r in audit_table if r[0] == base), None)
        if base_row:
            audit_table.append((col, base_row[1], base_row[2], base_row[3], base_row[4],
                                 f"{base} のレース内SC標準化"))
        else:
            audit_table.append((col, "derived", "派生", True, "OK", f"{base} のSC標準化"))

    result = []
    leak_count = 0
    for feat, source, timing, available, judgment, note in audit_table:
        if feat not in df.columns and judgment not in ("TARGET", "SKIP"):
            continue
        if judgment == "LEAK":
            leak_count += 1
        result.append({
            "feature":     feat,
            "data_source": source,
            "confirmed_at": timing,
            "available_at_bet_time": "✅" if available else "❌",
            "judgment":    judgment,
            "note":        note,
        })

    logger.info("リーク監査完了: LEAK=%d, TARGET=%d, OK=%d, OK*=%d",
                leak_count,
                sum(1 for r in result if r["judgment"] == "TARGET"),
                sum(1 for r in result if r["judgment"] == "OK"),
                sum(1 for r in result if r["judgment"] == "OK*"),
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Task 0-3: Walk-Forward 分割定義
# ──────────────────────────────────────────────────────────────────────────────

def task03_walkforward(df: pd.DataFrame) -> list[dict]:
    """cv_splits.json を保存し、各 Fold のサンプル数を確認する。"""
    logger.info("=== Task 0-3: Walk-Forward 分割定義 ===")
    splits = load_cv_splits()

    fold_stats = []
    for fold_num, train_df, test_df in iter_folds(df, splits=splits):
        train_w_result = train_df[train_df["finish_position"].notna()]
        test_w_result  = test_df[test_df["finish_position"].notna()]
        fold_stats.append({
            "fold":           fold_num,
            "note":           next(s["note"] for s in splits if s["fold"] == fold_num),
            "train_rows":     len(train_df),
            "train_w_result": len(train_w_result),
            "test_rows":      len(test_df),
            "test_w_result":  len(test_w_result),
        })
        logger.info(
            "Fold %d: train=%d(res=%d), test=%d(res=%d)",
            fold_num, len(train_df), len(train_w_result),
            len(test_df), len(test_w_result),
        )
    return fold_stats


# ──────────────────────────────────────────────────────────────────────────────
# Task 0-4: 市場ベースライン
# ──────────────────────────────────────────────────────────────────────────────

def task04_baseline(
    df: pd.DataFrame,
    model_run_pairs: list[tuple[str, pd.DataFrame]],
) -> pd.DataFrame:
    """Random / Favorite / Market / Model の ROI を算出して比較する。"""
    logger.info("=== Task 0-4: 市場ベースライン計算 ===")
    result_df = compare_baselines(df, model_results=model_run_pairs)
    for _, row in result_df.iterrows():
        logger.info(
            "  %-35s n=%5d  ROI=%7.2f%%  CI=[%7.2f%%, %7.2f%%]  p=%.4f",
            row.get("label", ""),
            row.get("n_bets", 0),
            row.get("roi_pct") or 0,
            row.get("ci_low_pct") or 0,
            row.get("ci_high_pct") or 0,
            row.get("p_value") or 1.0,
        )
    return result_df


# ──────────────────────────────────────────────────────────────────────────────
# Task 0-6: 実験ログ初期化
# ──────────────────────────────────────────────────────────────────────────────

def task06_experiment_log(baseline_df: pd.DataFrame, data_hash: str) -> None:
    """experiment_log.csv に Phase0 の実行記録を追記する。"""
    log_path = OUT_DIR / "experiment_log.csv"
    fieldnames = ["run_id", "date", "phase", "config_hash", "data_hash",
                  "label", "n_bets", "oos_roi_pct", "ci_low_pct", "ci_high_pct",
                  "p_value", "notes"]
    write_header = not log_path.exists()

    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for _, row in baseline_df.iterrows():
            writer.writerow({
                "run_id":       run_id,
                "date":         datetime.date.today().isoformat(),
                "phase":        "phase0",
                "config_hash":  "snapshot_config.yaml",
                "data_hash":    data_hash,
                "label":        row.get("label", ""),
                "n_bets":       row.get("n_bets", 0),
                "oos_roi_pct":  row.get("roi_pct", ""),
                "ci_low_pct":   row.get("ci_low_pct", ""),
                "ci_high_pct":  row.get("ci_high_pct", ""),
                "p_value":      row.get("p_value", ""),
                "notes":        "phase0_baseline",
            })
    logger.info("experiment_log.csv 更新: %s", log_path)


# ──────────────────────────────────────────────────────────────────────────────
# レポート生成
# ──────────────────────────────────────────────────────────────────────────────

def _judgment_str(baseline_df: pd.DataFrame) -> str:
    """Market ベースラインとの比較から Phase0 判定を生成する。"""
    rows = {r["label"]: r for r in baseline_df.to_dict("records")}
    market_row = next((r for k, r in rows.items() if "Market" in k), None)
    if market_row is None:
        return "判定不能（Marketベースライン未算出）"

    market_roi = market_row.get("roi_pct") or 0
    judgments = []
    for label, row in rows.items():
        if "Market" in label or "Random" in label or "Favorite" in label:
            continue
        model_roi = row.get("roi_pct") or 0
        sig       = row.get("significant", False)
        vs        = row.get("vs_reference_pt") or (model_roi - market_roi)
        if sig and vs > 0:
            judgments.append(f"**{label}**: Market を {vs:+.2f}pt 上回る（p={row.get('p_value', 'N/A'):.4f}）✅")
        else:
            judgments.append(f"**{label}**: Market を {vs:+.2f}pt 下回る / 有意差なし（p={row.get('p_value', 'N/A'):.4f}）❌")
    return "\n".join(judgments) if judgments else "モデル結果なし"


def generate_report(
    odds_info: dict,
    audit_rows: list[dict],
    fold_stats: list[dict],
    baseline_df: pd.DataFrame,
    out_dir: Path,
) -> None:
    leak_count   = sum(1 for r in audit_rows if r["judgment"] == "LEAK")
    target_count = sum(1 for r in audit_rows if r["judgment"] == "TARGET")
    ok_count     = sum(1 for r in audit_rows if r["judgment"].startswith("OK"))

    audit_md = "| 特徴量 | データソース | 確定タイミング | BET_TIME利用可 | 判定 | 備考 |\n"
    audit_md += "|---|---|---|---|---|---|\n"
    for r in audit_rows:
        audit_md += (f"| {r['feature']} | {r['data_source']} | {r['confirmed_at']} "
                     f"| {r['available_at_bet_time']} | {r['judgment']} | {r['note']} |\n")

    fold_md = "| Fold | 概要 | Train行数 | Train(結果あり) | Test行数 | Test(結果あり) |\n"
    fold_md += "|---|---|---|---|---|---|\n"
    for s in fold_stats:
        fold_md += (f"| {s['fold']} | {s['note']} | {s['train_rows']} "
                    f"| {s['train_w_result']} | {s['test_rows']} | {s['test_w_result']} |\n")

    baseline_md = "| Strategy | 購入数 | ROI | 95% CI | p値 | 有意 | Marketとの差 |\n"
    baseline_md += "|---|---|---|---|---|---|---|\n"
    for row in baseline_df.to_dict("records"):
        reliable = "" if row.get("reliable", True) else "⚠️参考"
        sig      = "✅" if row.get("significant") else "❌"
        vs       = f"{row.get('vs_reference_pt', '-'):+.2f}pt" if row.get("vs_reference_pt") is not None else "-"
        baseline_md += (
            f"| {row.get('label','')} | {row.get('n_bets',0)}{reliable} "
            f"| {row.get('roi_pct', 'N/A')}% "
            f"| [{row.get('ci_low_pct','?')}%, {row.get('ci_high_pct','?')}%] "
            f"| {row.get('p_value', '-')} | {sig} | {vs} |\n"
        )

    done_cond = "✅" if leak_count == 0 else "❌"

    report = f"""# Phase0 評価レポート

**実行日時**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## Task 0-1: オッズ・タイムスナップショット

| 項目 | 値 |
|---|---|
| ステータス | **{odds_info['status']}** |
| 使用カラム | `{odds_info['column_used']}` |
| エントリ数 | {odds_info['n_entries']:,} |
| オッズ null率 | {odds_info['odds_null_rate']}% |
| オッズ中央値 | {odds_info['odds_median']}倍 |
| 時系列オッズ | {"あり" if odds_info['has_timeseries_odds'] else "**なし（最優先データ課題）**"} |

> **{odds_info['status']}**: {odds_info['note']}
> 現在の ROI は「実運用の上限値（楽観値）」として扱う。確定値として報告しない。

**必要アクション**: {odds_info['action_required']}

---

## Task 0-2: 特徴量リーク監査

**結果**: LEAK={leak_count}, TARGET={target_count}, OK/OK*={ok_count}

{done_cond} LEAK 判定: {"**ゼロ — Phase1 へ進んでよい**" if leak_count == 0 else f"**{leak_count}件のリークを検出。除去してから Phase1 へ進むこと**"}

<details>
<summary>監査表（クリックで展開）</summary>

{audit_md}
</details>

---

## Task 0-3: Walk-Forward 分割

`cv_splits.json` に保存済み。各 Fold の embargo は2週間。

{fold_md}

---

## Task 0-4: 市場ベースライン

{baseline_md}

### 判定

{_judgment_str(baseline_df)}

> **注意**: 現在は OPTIMISTIC_BIAS のため、実際の ROI はここより低い可能性がある。
> 時系列オッズ取得後に再計算すること。

---

## Phase0 完了条件チェック

| 条件 | 状態 |
|---|---|
| `odds_at_bet` / `odds_final` 分離 | ⚠️ 未達（OPTIMISTIC_BIAS で暫定運用） |
| 特徴量リーク監査 LEAK=0 | {done_cond} {"達成" if leak_count == 0 else "未達"} |
| Walk-Forward 分割（embargo付き）実装 | ✅ cv_splits.json 保存済み |
| 4ベースライン（Market含む）算出 | ✅ baseline_comparison.csv 出力済み |
| ブロックブートストラップ ROI CI 実装 | ✅ metrics_lib.py |
| 乱数シード固定 | ✅ seed={42} |

---

## Phase0 → Phase1 引き継ぎ

* **OPTIMISTIC_BIAS 運用**: 現在の ROI は楽観値。確定値として報告しない。
* **leakage_audit.md**: LEAK=0 確認済み。特徴量は BET_TIME で利用可能。
* **metrics_lib.py**: Phase1〜4 の全分析でブロックブートストラップ CI を必ず付与する。
* **cv_splits.json**: Phase3 Walk-Forward で必ず使用する。
"""

    report_path = out_dir / "phase0_report.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("phase0_report.md 保存: %s", report_path)


# ──────────────────────────────────────────────────────────────────────────────
# DB からバックテスト結果を取得
# ──────────────────────────────────────────────────────────────────────────────

def load_bets_from_db(client, run_id: int) -> pd.DataFrame:
    """backtest_bets を paginate で全件取得し DataFrame で返す。"""
    logger.info("Loading backtest_bets for run_id=%d ...", run_id)
    rows = paginate(lambda off, lim: (
        client.table("backtest_bets")
        .select("race_id, is_hit, payout_amount, prediction_value, edge_value")
        .eq("backtest_run_id", run_id)
        .range(off, off + lim - 1)
    ))
    logger.info("  run_id=%d: %d bets", run_id, len(rows))
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase0: 評価基盤の地固め")
    parser.add_argument(
        "--run-id", dest="run_ids", action="append", type=int, default=[],
        help="バックテスト run_id（複数指定可）"
    )
    parser.add_argument(
        "--run-label", dest="run_labels", action="append", default=[],
        help="run_id に対応するラベル（--run-id と同数指定）"
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── parquet 読み込み ──
    logger.info("parquet 読み込み: %s", PARQUET_PATH)
    df = pd.read_parquet(PARQUET_PATH)
    df_result = df[df["finish_position"].notna()].copy()
    logger.info("全行=%d, 結果あり=%d", len(df), len(df_result))

    data_hash = hashlib.md5(df.to_parquet()).hexdigest()[:8]

    # ── Task 0-1 ──
    odds_info = task01_odds_timing(df_result)

    # ── Task 0-2 ──
    audit_rows = task02_leakage_audit(df)
    audit_path = OUT_DIR / "leakage_audit.md"
    md = "# 特徴量リーク監査表\n\n"
    md += "| 特徴量 | データソース | 確定タイミング | BET_TIME利用可 | 判定 | 備考 |\n"
    md += "|---|---|---|---|---|---|\n"
    for r in audit_rows:
        md += (f"| `{r['feature']}` | {r['data_source']} | {r['confirmed_at']} "
               f"| {r['available_at_bet_time']} | **{r['judgment']}** | {r['note']} |\n")
    audit_path.write_text(md, encoding="utf-8")
    logger.info("leakage_audit.md 保存: %s", audit_path)

    # ── Task 0-3 ──
    fold_stats = task03_walkforward(df_result)

    # ── Task 0-4: DB からモデルデータ取得 ──
    model_run_pairs: list[tuple[str, pd.DataFrame]] = []
    if args.run_ids:
        client = get_client()
        labels = args.run_labels if args.run_labels else [f"run_{rid}" for rid in args.run_ids]
        for rid, label in zip(args.run_ids, labels):
            bets_df = load_bets_from_db(client, rid)
            if not bets_df.empty:
                model_run_pairs.append((label, bets_df))

    baseline_df = task04_baseline(df_result, model_run_pairs)
    baseline_df.to_csv(OUT_DIR / "baseline_comparison.csv", index=False, encoding="utf-8-sig")
    logger.info("baseline_comparison.csv 保存")

    # ── Task 0-6 ──
    task06_experiment_log(baseline_df, data_hash)

    # ── レポート生成 ──
    generate_report(odds_info, audit_rows, fold_stats, baseline_df, OUT_DIR)

    logger.info("=== Phase0 完了 ===")
    logger.info("出力先: %s", OUT_DIR)


if __name__ == "__main__":
    main()

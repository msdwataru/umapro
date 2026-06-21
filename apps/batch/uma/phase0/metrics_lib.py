"""
Phase0 Task 0-5: 共通統計ライブラリ

全 Phase で使う ROI 信頼区間・有意性検定・ドローダウン関数。
ベット単位ではなく race_id 単位のブロックブートストラップを使う。
（同一レース内のベットは相関するため、単純ブートストラップは過信頼区間になる）
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RANDOM_SEED = 42
N_BETS_RELIABLE  = 200   # これ以上で信頼できる
N_BETS_REPORTABLE = 50   # これ未満は非表示（ノイズ）


def roi_ci(
    profits: np.ndarray,
    stakes: np.ndarray,
    race_ids: np.ndarray | None = None,
    n_boot: int = 10000,
    confidence: float = 0.95,
    random_seed: int = RANDOM_SEED,
) -> dict:
    """
    ブロックブートストラップ（race_id 単位）で ROI の信頼区間を計算する。

    Parameters
    ----------
    profits : ndarray
        各ベットの純利益（的中: payout - stake, 外れ: -stake）
    stakes : ndarray
        各ベットの購入金額
    race_ids : ndarray | None
        ブロック単位。指定時は race_id 単位でリサンプル（推奨）
    """
    profits  = np.asarray(profits,  dtype=float)
    stakes   = np.asarray(stakes,   dtype=float)
    rng      = np.random.default_rng(random_seed)
    n_bets   = len(profits)

    if n_bets == 0:
        return {"roi": np.nan, "ci_low": np.nan, "ci_high": np.nan,
                "n_bets": 0, "total_profit": 0.0, "total_stake": 0.0}

    total_profit = float(profits.sum())
    total_stake  = float(stakes.sum())
    roi          = total_profit / total_stake if total_stake > 0 else np.nan

    boot_rois = _bootstrap(profits, stakes, race_ids, rng, n_boot)

    alpha   = 1.0 - confidence
    ci_low  = float(np.percentile(boot_rois, alpha / 2 * 100))
    ci_high = float(np.percentile(boot_rois, (1 - alpha / 2) * 100))

    return {
        "roi":          roi,
        "ci_low":       ci_low,
        "ci_high":      ci_high,
        "n_bets":       n_bets,
        "total_profit": total_profit,
        "total_stake":  total_stake,
    }


def roi_significance(
    profits: np.ndarray,
    stakes: np.ndarray,
    race_ids: np.ndarray | None = None,
    null_roi: float = 0.0,
    n_boot: int = 10000,
    random_seed: int = RANDOM_SEED,
) -> float:
    """
    H0: ROI <= null_roi の片側検定。p値を返す。
    p < 0.05 で「ROI が null_roi を統計的有意に上回る」と言える。
    """
    profits = np.asarray(profits, dtype=float)
    stakes  = np.asarray(stakes,  dtype=float)
    rng     = np.random.default_rng(random_seed)

    if len(profits) == 0:
        return 1.0

    boot_rois = _bootstrap(profits, stakes, race_ids, rng, n_boot)
    return float((boot_rois <= null_roi).mean())


def _bootstrap(
    profits: np.ndarray,
    stakes: np.ndarray,
    race_ids: np.ndarray | None,
    rng: np.random.Generator,
    n_boot: int,
) -> np.ndarray:
    """
    内部共通: ベクトル化ブートストラップ ROI 分布を生成する。
    race_ids 指定時はレース単位でリサンプル（ブロックブートストラップ）。
    Python for ループを排除し numpy 行列演算に統一。
    """
    if race_ids is not None:
        race_ids = np.asarray(race_ids)
        unique   = np.unique(race_ids)
        n_races  = len(unique)

        # レースごとの合計を事前計算 → shape (n_races,)
        race_p = np.array([profits[race_ids == r].sum() for r in unique])
        race_s = np.array([stakes[race_ids == r].sum()  for r in unique])

        # (n_boot, n_races) インデックスを一括生成して行列和
        idx       = rng.integers(0, n_races, size=(n_boot, n_races))
        boot_p    = race_p[idx].sum(axis=1)
        boot_s    = race_s[idx].sum(axis=1)
    else:
        n      = len(profits)
        idx    = rng.integers(0, n, size=(n_boot, n))
        boot_p = profits[idx].sum(axis=1).astype(float)
        boot_s = stakes[idx].sum(axis=1).astype(float)

    with np.errstate(invalid="ignore", divide="ignore"):
        boot_rois = np.where(boot_s > 0, boot_p / boot_s, np.nan)

    arr = np.asarray(boot_rois, dtype=float)
    return arr[~np.isnan(arr)]


def drawdown(equity_curve: np.ndarray) -> dict:
    """エクイティカーブから最大ドローダウンを計算する。"""
    equity = np.asarray(equity_curve, dtype=float)
    if len(equity) == 0:
        return {"max_drawdown": 0.0, "max_drawdown_pct": 0.0,
                "drawdown_start": -1, "drawdown_end": -1}

    running_max = np.maximum.accumulate(equity)
    dd = equity - running_max
    min_idx  = int(np.argmin(dd))
    peak_idx = int(np.argmax(equity[:min_idx + 1])) if min_idx > 0 else 0
    max_dd   = float(-dd[min_idx])
    peak_val = float(running_max[min_idx])
    return {
        "max_drawdown":     max_dd,
        "max_drawdown_pct": (max_dd / peak_val * 100.0) if peak_val > 0 else 0.0,
        "drawdown_start":   peak_idx,
        "drawdown_end":     min_idx,
    }


def format_roi_row(
    label: str,
    result: dict,
    p_value: float | None = None,
    reference_roi: float | None = None,
) -> dict:
    """
    roi_ci() の結果を報告用 dict に整形する。全 Phase の表生成で共通利用。

    Parameters
    ----------
    reference_roi : float | None
        比較対象の ROI（例: Market の ROI）。指定時は「vs reference」列を追加。
    """
    def _pct(v):
        return round(float(v) * 100, 2) if v is not None and not np.isnan(v) else None

    row = {
        "label":          label,
        "n_bets":         result["n_bets"],
        "roi_pct":        _pct(result["roi"]),
        "ci_low_pct":     _pct(result["ci_low"]),
        "ci_high_pct":    _pct(result["ci_high"]),
        "total_profit":   round(result["total_profit"], 0),
        "total_stake":    round(result["total_stake"],  0),
        "reliable":       is_reliable(result["n_bets"]),
    }
    if p_value is not None:
        row["p_value"]     = round(p_value, 4)
        row["significant"] = p_value < 0.05
    if reference_roi is not None and row["roi_pct"] is not None:
        row["vs_reference_pt"] = round(row["roi_pct"] - reference_roi * 100, 2)
    return row


def is_reportable(n_bets: int) -> bool:
    return n_bets >= N_BETS_REPORTABLE


def is_reliable(n_bets: int) -> bool:
    return n_bets >= N_BETS_RELIABLE

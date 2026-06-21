"""
Phase0 Task 0-4: 市場ベースライン計算

Random / Favorite / Market（最重要）/ Model の ROI を算出する。
Market ベースラインが「市場効率の天井」。モデルがこれを超えて初めて優位性あり。

payout の計算:
  - 的中: latest_win_odds × stake  （払戻）
  - 外れ: 0
  - 利益: payout - stake
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from uma.phase0.metrics_lib import roi_ci, roi_significance, format_roi_row

STAKE = 100.0


def calc_random_baseline(
    df: pd.DataFrame,
    n_sim: int = 100,
    random_seed: int = 42,
) -> dict:
    """
    各レースでランダムに 1 頭を選択（Monte Carlo n_sim 回平均）。
    完全な床: 控除率ぶんだけ負ける ≒ -25%。
    """
    rng    = np.random.default_rng(random_seed)
    df_r   = df[df["finish_position"].notna()].copy()
    races  = df_r["race_id"].unique()

    all_profits:  list[float] = []
    all_stakes:   list[float] = []
    all_race_ids: list[int]   = []

    for _ in range(n_sim):
        for rid in races:
            grp = df_r[df_r["race_id"] == rid]
            if len(grp) == 0:
                continue
            chosen = grp.sample(1, random_state=int(rng.integers(0, 10**7))).iloc[0]
            won    = chosen["finish_position"] == 1
            profit = chosen["latest_win_odds"] * STAKE - STAKE if won else -STAKE
            all_profits.append(profit / n_sim)
            all_stakes.append(STAKE / n_sim)
            all_race_ids.append(rid)

    return roi_ci(
        np.array(all_profits),
        np.array(all_stakes),
        race_ids=np.array(all_race_ids),
    )


def calc_favorite_baseline(df: pd.DataFrame) -> dict:
    """各レースで odds_rank == 1（1番人気）の馬を購入。"""
    df_r  = df[df["finish_position"].notna() & (df["odds_rank"] == 1)].copy()
    won   = df_r["finish_position"] == 1
    profits  = np.where(won, df_r["latest_win_odds"] * STAKE - STAKE, -STAKE)
    stakes   = np.full(len(df_r), STAKE)
    return roi_ci(profits, stakes, race_ids=df_r["race_id"].values)


def calc_market_baseline(df: pd.DataFrame) -> dict:
    """
    市場確率 (1/odds) を race_id 内で正規化し、確率最大の馬を購入する。
    これが「市場効率の天井」。
    """
    df_r = df[df["finish_position"].notna()].copy()
    df_r["_odds_inv"]    = 1.0 / df_r["latest_win_odds"]
    df_r["_market_prob"] = df_r.groupby("race_id")["_odds_inv"].transform(
        lambda x: x / x.sum()
    )
    idx     = df_r.groupby("race_id")["_market_prob"].idxmax()
    chosen  = df_r.loc[idx]
    won     = chosen["finish_position"] == 1
    profits = np.where(won, chosen["latest_win_odds"] * STAKE - STAKE, -STAKE)
    stakes  = np.full(len(chosen), STAKE)
    return roi_ci(profits, stakes, race_ids=chosen["race_id"].values)


def calc_model_baseline(
    bets_df: pd.DataFrame,
) -> dict:
    """
    backtest_bets テーブルから読み込んだベット結果の ROI を計算する。

    Parameters
    ----------
    bets_df : DataFrame
        カラム: is_hit (bool), payout_amount (float), race_id (int)
    """
    profits  = np.where(
        bets_df["is_hit"],
        bets_df["payout_amount"].fillna(0).astype(float) - STAKE,
        -STAKE,
    )
    stakes   = np.full(len(bets_df), STAKE)
    race_ids = bets_df["race_id"].values if "race_id" in bets_df.columns else None
    return roi_ci(profits, stakes, race_ids=race_ids)


def compare_baselines(
    df: pd.DataFrame,
    model_results: list[tuple[str, pd.DataFrame]] | None = None,
    n_sim: int = 100,
    random_seed: int = 42,
) -> pd.DataFrame:
    """
    4 種のベースラインを一括計算して DataFrame で返す。

    Parameters
    ----------
    df : pd.DataFrame
        parquet（finish_position あり行のみ使用）
    model_results : list of (label, bets_df) | None
        モデル毎のバックテスト結果。複数モデルを同時比較できる。
    """
    rows = []

    # ── Random ──
    r_rand = calc_random_baseline(df, n_sim=n_sim, random_seed=random_seed)
    rows.append(format_roi_row("Random（ランダム）", r_rand))

    # ── Favorite ──
    r_fav = calc_favorite_baseline(df)
    df_fav = df[df["finish_position"].notna() & (df["odds_rank"] == 1)].copy()
    fav_won = df_fav["finish_position"] == 1
    fav_p   = roi_significance(
        np.where(fav_won, df_fav["latest_win_odds"] * STAKE - STAKE, -STAKE),
        np.full(len(df_fav), STAKE),
        race_ids=df_fav["race_id"].values,
    )
    rows.append(format_roi_row("Favorite（1番人気）", r_fav, p_value=fav_p))

    # ── Market（天井） ──
    r_mkt = calc_market_baseline(df)
    df_r = df[df["finish_position"].notna()].copy()
    df_r["_oi"] = 1.0 / df_r["latest_win_odds"]
    df_r["_mp"] = df_r.groupby("race_id")["_oi"].transform(lambda x: x / x.sum())
    mkt_chosen  = df_r.loc[df_r.groupby("race_id")["_mp"].idxmax()]
    mkt_won     = mkt_chosen["finish_position"] == 1
    mkt_p = roi_significance(
        np.where(mkt_won, mkt_chosen["latest_win_odds"] * STAKE - STAKE, -STAKE),
        np.full(len(mkt_chosen), STAKE),
        race_ids=mkt_chosen["race_id"].values,
    )
    market_roi = r_mkt["roi"]
    rows.append(format_roi_row("Market（市場確率最大）★天井", r_mkt, p_value=mkt_p))

    # ── Model（複数） ──
    if model_results:
        for label, bets_df in model_results:
            r_model = calc_model_baseline(bets_df)
            model_profits = np.where(
                bets_df["is_hit"],
                bets_df["payout_amount"].fillna(0).astype(float) - STAKE,
                -STAKE,
            )
            model_stakes = np.full(len(bets_df), STAKE)
            race_ids     = bets_df["race_id"].values if "race_id" in bets_df.columns else None
            model_p = roi_significance(
                model_profits, model_stakes,
                race_ids=race_ids,
                null_roi=market_roi,  # vs Market baseline
            )
            rows.append(format_roi_row(
                label, r_model, p_value=model_p, reference_roi=market_roi
            ))

    return pd.DataFrame(rows)

"""
LightGBM Ranker による予測生成。

artifacts/race_features_v1.parquet と artifacts/lgbm_ranker_v1.txt を使って
model_predictions テーブルに書き込む。

  predicted_value    = softmax(score_i)  ← レース内推定勝率
  implied_probability = (1/odds_i) / Σ(1/odds_j)  ← 市場確率
  edge_value         = predicted_value - implied_probability
"""

from __future__ import annotations

import logging
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from supabase import Client

logger = logging.getLogger(__name__)

_ARTIFACTS_DIR     = Path(__file__).parent.parent.parent / "artifacts"
_PARQUET_PATH      = _ARTIFACTS_DIR / "race_features_v1.parquet"
_MODEL_PATH        = _ARTIFACTS_DIR / "lgbm_ranker_v1.txt"

_FEATURE_SET_NAME  = "lgbm_ranker_v1"
_FEATURE_SET_VER   = "v1"
_MODEL_NAME        = "lgbm_ranker"
_MODEL_VERSION     = "v1"
_PREDICTION_TARGET = "win"
_BATCH_SIZE        = 500

_EXCLUDE_COLS = {
    "race_entry_id", "race_id", "race_date",
    "finish_position", "finish_time_sec",
    "jockey_affiliation_enc",
}
_CAT_COLS = ["sire_name", "dam_name"]


def ensure_feature_set(client: Client) -> int:
    result = (
        client.table("feature_sets")
        .select("id")
        .eq("feature_set_name", _FEATURE_SET_NAME)
        .eq("version", _FEATURE_SET_VER)
        .single()
        .execute()
    )
    return result.data["id"]


def ensure_model_version(client: Client, feature_set_id: int) -> int:
    result = (
        client.table("model_versions")
        .select("id")
        .eq("model_name", _MODEL_NAME)
        .eq("version", _MODEL_VERSION)
        .single()
        .execute()
    )
    return result.data["id"]


def generate(
    client: Client,
    model_version_id: int,
    feature_set_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int:
    # ── データロード ──────────────────────────────────────────────────
    df = pd.read_parquet(_PARQUET_PATH)

    if start_date:
        df = df[df["race_date"] >= start_date]
    if end_date:
        df = df[df["race_date"] <= end_date]

    if df.empty:
        logger.warning("対象データが 0 件です (start=%s end=%s)", start_date, end_date)
        return 0

    logger.info("Predicting %d rows (%d races)", len(df), df["race_id"].nunique())

    # ── 特徴量準備 ────────────────────────────────────────────────────
    feat_cols = [c for c in df.columns if c not in _EXCLUDE_COLS]
    for col in _CAT_COLS:
        if col in feat_cols:
            df[col] = df[col].astype("category")

    # ── モデルロード & スコア計算 ─────────────────────────────────────
    booster = lgb.Booster(model_file=str(_MODEL_PATH))
    scores  = booster.predict(df[feat_cols])
    df["_score"] = scores

    # ── レース単位で確率化・ランク付け ───────────────────────────────
    payloads: list[dict] = []

    for race_id, grp in df.groupby("race_id", sort=False):
        sc       = grp["_score"].values.astype(float)
        odds_inv = grp["odds_inv"].values.astype(float)

        # softmax でレース内勝率に変換
        sc_shifted   = sc - sc.max()
        exp_sc       = np.exp(sc_shifted)
        predicted    = exp_sc / exp_sc.sum()

        # 市場確率（オッズ逆数の正規化）
        implied      = odds_inv / odds_inv.sum()

        edge         = predicted - implied
        ranks        = np.argsort(np.argsort(-sc)) + 1  # 1 = 最高スコア

        race_date    = grp["race_date"].iloc[0]
        predicted_at = f"{race_date}T10:00:00+09:00"

        for i, (_, row) in enumerate(grp.iterrows()):
            payloads.append({
                "race_entry_id":      int(row["race_entry_id"]),
                "model_version_id":   model_version_id,
                "feature_set_id":     feature_set_id,
                "prediction_target":  _PREDICTION_TARGET,
                "predicted_value":    round(float(predicted[i]), 6),
                "implied_probability": round(float(implied[i]), 6),
                "edge_value":         round(float(edge[i]),     6),
                "prediction_rank":    int(ranks[i]),
                "predicted_at":       predicted_at,
            })

        # バッチ書き込み
        if len(payloads) >= _BATCH_SIZE:
            client.table("model_predictions").upsert(
                payloads,
                on_conflict="race_entry_id,model_version_id,prediction_target,predicted_at",
            ).execute()
            logger.info("Upserted %d predictions", len(payloads))
            payloads = []

    # 残り書き込み
    if payloads:
        client.table("model_predictions").upsert(
            payloads,
            on_conflict="race_entry_id,model_version_id,prediction_target,predicted_at",
        ).execute()
        logger.info("Upserted %d predictions", len(payloads))

    total = len(df)
    logger.info("generate() done: %d predictions", total)
    return total

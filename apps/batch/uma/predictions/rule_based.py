"""
市場正規化モデルによるルールベース予測生成。

各レース内で 1/odds を正規化して予測確率を算出し model_predictions に書き込む。
  predicted_value    = (1/odds_i) / Σ(1/odds_j)  ← 正規化後の市場確率
  implied_probability = 1/odds_i                   ← オッズ逆数（生値）
  edge_value         = predicted_value - implied_probability
"""

from __future__ import annotations

import logging
from itertools import groupby
from typing import Any

from supabase import Client

from uma.db.client import paginate

logger = logging.getLogger(__name__)

_FEATURE_SET_NAME = "market_baseline"
_FEATURE_SET_VERSION = "v1"
_MODEL_NAME = "rule_based_market"
_MODEL_VERSION = "v1"
_PREDICTION_TARGET = "win"
_BATCH_SIZE = 500  # upsert per call


def ensure_feature_set(client: Client) -> int:
    result = (
        client.table("feature_sets")
        .upsert(
            {
                "feature_set_name": _FEATURE_SET_NAME,
                "version": _FEATURE_SET_VERSION,
                "description": "オッズの逆数をレース内で正規化した市場ベースラインモデル",
                "feature_schema_json": {"features": ["latest_win_odds"]},
                "is_active": True,
            },
            on_conflict="feature_set_name,version",
        )
        .execute()
    )
    return result.data[0]["id"]


def ensure_model_version(client: Client, feature_set_id: int) -> int:
    result = (
        client.table("model_versions")
        .upsert(
            {
                "model_name": _MODEL_NAME,
                "version": _MODEL_VERSION,
                "model_type": "rule_based",
                "feature_set_id": feature_set_id,
                "is_production": True,
            },
            on_conflict="model_name,version",
        )
        .execute()
    )
    return result.data[0]["id"]


def _predicted_at(race: dict[str, Any]) -> str:
    if race.get("scheduled_start_at"):
        return race["scheduled_start_at"]
    return f"{race['race_date']}T10:00:00+09:00"


def generate(
    client: Client,
    model_version_id: int,
    feature_set_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int:
    """
    全 race_entries から予測値を計算して model_predictions に upsert する。
    start_date / end_date (YYYY-MM-DD) で対象レースの race_date を絞り込める。
    返り値は書き込んだレコード数。
    """
    entries = paginate(lambda off, lim: (
        client.table("race_entries")
        .select("id, race_id, latest_win_odds, races(race_date, scheduled_start_at)")
        .eq("scratch_flag", False)
        .filter("latest_win_odds", "not.is", "null")
        .range(off, off + lim - 1)
    ))

    if start_date:
        entries = [e for e in entries if e["races"]["race_date"] >= start_date]
    if end_date:
        entries = [e for e in entries if e["races"]["race_date"] <= end_date]

    logger.info("Fetched %d race_entries with odds (start=%s, end=%s)", len(entries), start_date, end_date)

    # race_id でソートしてグループ化
    entries_sorted = sorted(entries, key=lambda e: e["race_id"])
    payloads: list[dict] = []
    total = 0

    for _, group in groupby(entries_sorted, key=lambda e: e["race_id"]):
        race_entries = list(group)
        race = race_entries[0]["races"]

        # 1/odds を計算
        inv_odds_list = [(e, 1.0 / float(e["latest_win_odds"])) for e in race_entries]
        total_inv = sum(io for _, io in inv_odds_list)

        # predicted_value 降順でソートして rank 付け
        ranked = sorted(inv_odds_list, key=lambda x: -x[1])
        pat = _predicted_at(race)

        for rank, (entry, inv_odds) in enumerate(ranked, 1):
            predicted_value = inv_odds / total_inv
            implied_probability = inv_odds
            edge_value = predicted_value - implied_probability

            payloads.append(
                {
                    "race_entry_id": entry["id"],
                    "model_version_id": model_version_id,
                    "feature_set_id": feature_set_id,
                    "prediction_target": _PREDICTION_TARGET,
                    "predicted_value": round(predicted_value, 6),
                    "implied_probability": round(implied_probability, 6),
                    "edge_value": round(edge_value, 6),
                    "prediction_rank": rank,
                    "predicted_at": pat,
                }
            )

        # バッチサイズに達したら書き込み
        if len(payloads) >= _BATCH_SIZE:
            client.table("model_predictions").upsert(
                payloads,
                on_conflict="race_entry_id,model_version_id,prediction_target,predicted_at",
            ).execute()
            total += len(payloads)
            logger.info("Upserted %d predictions (total=%d)", len(payloads), total)
            payloads = []

    # 残りを書き込み
    if payloads:
        client.table("model_predictions").upsert(
            payloads,
            on_conflict="race_entry_id,model_version_id,prediction_target,predicted_at",
        ).execute()
        total += len(payloads)
        logger.info("Upserted %d predictions (total=%d)", len(payloads), total)

    return total

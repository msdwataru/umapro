"""
複勝オッズベースモデル。

単勝の代わりに複勝オッズ（min+max の中央値）の逆数をレース内で正規化する。
複勝市場は単勝より非効率が出やすく、より良いシグナルになり得る。
"""

from __future__ import annotations

import logging
from itertools import groupby
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)

_FEATURE_SET_NAME = "market_place_baseline"
_FEATURE_SET_VERSION = "v1"
_MODEL_NAME = "place_odds_market"
_MODEL_VERSION = "v1"
_PREDICTION_TARGET = "win"
_BATCH_SIZE = 500


def ensure_feature_set(client: Client) -> int:
    result = (
        client.table("feature_sets")
        .upsert(
            {
                "feature_set_name": _FEATURE_SET_NAME,
                "version": _FEATURE_SET_VERSION,
                "description": "複勝オッズ（min+max中央値）の逆数をレース内で正規化した市場ベースラインモデル",
                "feature_schema_json": {"features": ["latest_place_odds_min", "latest_place_odds_max"]},
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
    entries = (
        client.table("race_entries")
        .select(
            "id, race_id, latest_place_odds_min, latest_place_odds_max,"
            "races(race_date, scheduled_start_at)"
        )
        .eq("scratch_flag", False)
        .filter("latest_place_odds_min", "not.is", "null")
        .filter("latest_place_odds_max", "not.is", "null")
        .execute()
    ).data

    if start_date:
        entries = [e for e in entries if e["races"]["race_date"] >= start_date]
    if end_date:
        entries = [e for e in entries if e["races"]["race_date"] <= end_date]

    logger.info("place_odds_model: fetched %d entries (start=%s, end=%s)", len(entries), start_date, end_date)

    entries_sorted = sorted(entries, key=lambda e: e["race_id"])
    payloads: list[dict] = []
    total = 0

    for _, group in groupby(entries_sorted, key=lambda e: e["race_id"]):
        race_entries = list(group)
        race = race_entries[0]["races"]

        inv_list = []
        for e in race_entries:
            place_min = float(e["latest_place_odds_min"])
            place_max = float(e["latest_place_odds_max"])
            place_mid = (place_min + place_max) / 2.0
            if place_mid <= 0:
                continue
            inv_list.append((e, 1.0 / place_mid))

        if not inv_list:
            continue

        total_inv = sum(iv for _, iv in inv_list)
        ranked = sorted(inv_list, key=lambda x: -x[1])
        pat = _predicted_at(race)

        for rank, (entry, inv) in enumerate(ranked, 1):
            predicted_value = inv / total_inv
            implied_probability = inv
            payloads.append({
                "race_entry_id": entry["id"],
                "model_version_id": model_version_id,
                "feature_set_id": feature_set_id,
                "prediction_target": _PREDICTION_TARGET,
                "predicted_value": round(predicted_value, 6),
                "implied_probability": round(implied_probability, 6),
                "edge_value": round(predicted_value - implied_probability, 6),
                "prediction_rank": rank,
                "predicted_at": pat,
            })

        if len(payloads) >= _BATCH_SIZE:
            client.table("model_predictions").upsert(
                payloads,
                on_conflict="race_entry_id,model_version_id,prediction_target,predicted_at",
            ).execute()
            total += len(payloads)
            logger.info("upserted %d (total=%d)", len(payloads), total)
            payloads = []

    if payloads:
        client.table("model_predictions").upsert(
            payloads,
            on_conflict="race_entry_id,model_version_id,prediction_target,predicted_at",
        ).execute()
        total += len(payloads)

    logger.info("place_odds_model: done total=%d", total)
    return total

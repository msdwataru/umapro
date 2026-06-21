"""
オッズドリフトモデル。

朝の人気順位（morning_line_popularity）と最新オッズの乖離を edge_value にする。
最新オッズで朝より支持が集まった馬 → 正の edge_value が出る唯一のモデル。
"""

from __future__ import annotations

import logging
from itertools import groupby
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)

_FEATURE_SET_NAME = "market_odds_drift"
_FEATURE_SET_VERSION = "v1"
_MODEL_NAME = "odds_drift"
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
                "description": "朝の人気順位 vs 最新オッズの乖離量をシグナルにするドリフトモデル",
                "feature_schema_json": {"features": ["morning_line_popularity", "latest_win_odds"]},
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
            "id, race_id, latest_win_odds, morning_line_popularity,"
            "races(race_date, scheduled_start_at)"
        )
        .eq("scratch_flag", False)
        .filter("latest_win_odds", "not.is", "null")
        .filter("morning_line_popularity", "not.is", "null")
        .execute()
    ).data

    if start_date:
        entries = [e for e in entries if e["races"]["race_date"] >= start_date]
    if end_date:
        entries = [e for e in entries if e["races"]["race_date"] <= end_date]

    logger.info("odds_drift_model: fetched %d entries (start=%s, end=%s)", len(entries), start_date, end_date)

    entries_sorted = sorted(entries, key=lambda e: e["race_id"])
    payloads: list[dict] = []
    total = 0

    for _, group in groupby(entries_sorted, key=lambda e: e["race_id"]):
        race_entries = list(group)
        race = race_entries[0]["races"]

        # 朝の人気逆数（順位の逆数で朝の支持シェアを近似）
        morning_list = []
        odds_list = []
        for e in race_entries:
            pop = float(e["morning_line_popularity"])
            odds = float(e["latest_win_odds"])
            if pop <= 0 or odds <= 0:
                continue
            morning_list.append((e, 1.0 / pop))
            odds_list.append((e, 1.0 / odds))

        if not morning_list or not odds_list:
            continue

        # 馬IDで辞書化
        morning_dict = {e["id"]: inv for e, inv in morning_list}
        odds_dict = {e["id"]: inv for e, inv in odds_list}

        # 両方存在する馬のみ対象
        valid_ids = set(morning_dict.keys()) & set(odds_dict.keys())
        if not valid_ids:
            continue

        morning_total = sum(v for eid, v in morning_dict.items() if eid in valid_ids)
        odds_total = sum(v for eid, v in odds_dict.items() if eid in valid_ids)

        if morning_total == 0 or odds_total == 0:
            continue

        # ランキングは最新オッズ基準（支持が高い馬を上位）
        valid_entries_map = {e["id"]: e for e in race_entries if e["id"] in valid_ids}
        ranked = sorted(valid_ids, key=lambda eid: -odds_dict[eid])

        pat = _predicted_at(race)

        for rank, eid in enumerate(ranked, 1):
            odds_norm = odds_dict[eid] / odds_total
            morning_norm = morning_dict[eid] / morning_total
            edge_value = odds_norm - morning_norm  # 正 = 朝より支持増加
            payloads.append({
                "race_entry_id": eid,
                "model_version_id": model_version_id,
                "feature_set_id": feature_set_id,
                "prediction_target": _PREDICTION_TARGET,
                "predicted_value": round(odds_norm, 6),
                "implied_probability": round(morning_norm, 6),
                "edge_value": round(edge_value, 6),
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

    logger.info("odds_drift_model: done total=%d", total)
    return total

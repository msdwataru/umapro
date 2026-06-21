"""
コース・距離適性モデル。

各馬のコース×距離帯（200m単位）での過去勝率を集計し、
市場オッズに適性スコアを掛け合わせて予測値を算出する。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import groupby
from typing import Any

from supabase import Client

from uma.db.client import paginate

logger = logging.getLogger(__name__)

_FEATURE_SET_NAME = "course_form_baseline"
_FEATURE_SET_VERSION = "v1"
_MODEL_NAME = "course_form"
_MODEL_VERSION = "v1"
_PREDICTION_TARGET = "win"
_BATCH_SIZE = 500
_ALPHA = 2.0  # コース適性の重み（0なら市場オッズのみ）
_MIN_SAMPLES = 3  # これ未満は勝率0.5（中立）として扱う


def ensure_feature_set(client: Client) -> int:
    result = (
        client.table("feature_sets")
        .upsert(
            {
                "feature_set_name": _FEATURE_SET_NAME,
                "version": _FEATURE_SET_VERSION,
                "description": "同コース・距離帯での過去勝率を市場オッズに掛け合わせた適性モデル（α=2.0）",
                "feature_schema_json": {
                    "features": ["latest_win_odds", "horse_id", "track_type", "distance_m"],
                    "alpha": _ALPHA,
                    "min_samples": _MIN_SAMPLES,
                    "dist_bucket_size": 200,
                },
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


def _dist_bucket(distance_m: int | None) -> int | None:
    if distance_m is None:
        return None
    return round(distance_m / 200) * 200


def _build_win_rate_index(client: Client) -> dict[tuple, float]:
    """
    horse_id × (track_type, dist_bucket) の過去勝率を全件集計してメモリに返す。
    """
    logger.info("course_form: loading entry_results for win rate index...")

    # race_entries + entry_results を結合して全出走歴を取得
    results = paginate(lambda off, lim: (
        client.table("entry_results")
        .select("race_entry_id, finish_position, race_entries(horse_id, races(track_type, distance_m))")
        .filter("finish_position", "not.is", "null")
        .range(off, off + lim - 1)
    ))

    logger.info("course_form: loaded %d entry_results", len(results))

    # horse_id × (track_type, dist_bucket) 別に出走・勝利を集計
    runs: dict[tuple, int] = defaultdict(int)
    wins: dict[tuple, int] = defaultdict(int)

    for r in results:
        entry = r.get("race_entries")
        if not entry:
            continue
        horse_id = entry.get("horse_id")
        race = entry.get("races")
        if not horse_id or not race:
            continue
        track_type = race.get("track_type")
        bucket = _dist_bucket(race.get("distance_m"))
        if not track_type or bucket is None:
            continue

        key = (horse_id, track_type, bucket)
        runs[key] += 1
        if r.get("finish_position") == 1:
            wins[key] += 1

    # 勝率マップ（サンプル不足は 0.5）
    win_rate: dict[tuple, float] = {}
    for key, n in runs.items():
        win_rate[key] = wins.get(key, 0) / n if n >= _MIN_SAMPLES else 0.5

    logger.info("course_form: win_rate index built for %d horse×course×dist combinations", len(win_rate))
    return win_rate


def generate(
    client: Client,
    model_version_id: int,
    feature_set_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int:
    win_rate_index = _build_win_rate_index(client)

    entries = paginate(lambda off, lim: (
        client.table("race_entries")
        .select(
            "id, race_id, horse_id, latest_win_odds,"
            "races(race_date, scheduled_start_at, track_type, distance_m)"
        )
        .eq("scratch_flag", False)
        .filter("latest_win_odds", "not.is", "null")
        .filter("horse_id", "not.is", "null")
        .range(off, off + lim - 1)
    ))

    if start_date:
        entries = [e for e in entries if e["races"]["race_date"] >= start_date]
    if end_date:
        entries = [e for e in entries if e["races"]["race_date"] <= end_date]

    logger.info("course_form: fetched %d entries (start=%s, end=%s)", len(entries), start_date, end_date)

    entries_sorted = sorted(entries, key=lambda e: e["race_id"])
    payloads: list[dict] = []
    total = 0

    for _, group in groupby(entries_sorted, key=lambda e: e["race_id"]):
        race_entries = list(group)
        race = race_entries[0]["races"]
        track_type = race.get("track_type")
        bucket = _dist_bucket(race.get("distance_m"))

        inv_list = []
        for e in race_entries:
            odds = float(e["latest_win_odds"])
            if odds <= 0:
                continue
            odds_inv = 1.0 / odds

            horse_id = e.get("horse_id")
            key = (horse_id, track_type, bucket)
            wr = win_rate_index.get(key, 0.5) if (track_type and bucket) else 0.5
            course_bonus = 1.0 + _ALPHA * (wr - 0.5)
            score = odds_inv * course_bonus
            inv_list.append((e, odds_inv, score))

        if not inv_list:
            continue

        total_odds_inv = sum(x[1] for x in inv_list)
        total_score = sum(x[2] for x in inv_list)
        if total_odds_inv == 0 or total_score == 0:
            continue

        ranked = sorted(inv_list, key=lambda x: -x[2])
        pat = _predicted_at(race)

        for rank, (entry, odds_inv, score) in enumerate(ranked, 1):
            odds_norm = odds_inv / total_odds_inv
            predicted_value = score / total_score
            # edge_value = コース適性による市場オッズとのズレ
            edge_value = predicted_value - odds_norm
            payloads.append({
                "race_entry_id": entry["id"],
                "model_version_id": model_version_id,
                "feature_set_id": feature_set_id,
                "prediction_target": _PREDICTION_TARGET,
                "predicted_value": round(predicted_value, 6),
                "implied_probability": round(odds_norm, 6),
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

    logger.info("course_form: done total=%d", total)
    return total

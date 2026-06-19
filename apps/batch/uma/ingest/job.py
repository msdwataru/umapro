"""
毎朝実行するデータ取得ジョブ。
netkeibaから当日のレース・出馬表・オッズを取得してSupabaseへ格納する。

Usage:
    uv run python -m uma.ingest.job
    uv run python -m uma.ingest.job --date 2026-06-21
"""
import argparse
import logging
from datetime import date

from uma.db.client import get_client
from uma.db.upsert import upsert_records
from uma.ingest.netkeiba import fetch_odds, fetch_race_detail, fetch_race_list
from uma.jobs.base import job_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _ensure_racecourse(client, code: str, name: str, short_name: str) -> int:
    result = (
        client.table("racecourses")
        .upsert(
            {
                "external_racecourse_code": code,
                "name": name,
                "short_name": short_name,
                "is_active": True,
            },
            on_conflict="external_racecourse_code",
        )
        .execute()
    )
    return result.data[0]["id"]


def _ensure_horse(client, external_code: str, name: str, sex: str | None) -> int | None:
    if not external_code:
        return None
    result = (
        client.table("horses")
        .upsert(
            {"external_horse_code": external_code, "name": name, "sex": sex},
            on_conflict="external_horse_code",
        )
        .execute()
    )
    return result.data[0]["id"]


def _ensure_person(client, table: str, external_code: str, name: str) -> int | None:
    """jockeys / trainers テーブルへupsert。テーブル名から末尾のsを除いた単数形でカラム名を生成"""
    if not external_code:
        return None
    # "jockeys" -> "jockey", "trainers" -> "trainer"
    singular = table.rstrip("s")
    col = f"external_{singular}_code"
    result = (
        client.table(table)
        .upsert({col: external_code, "name": name}, on_conflict=col)
        .execute()
    )
    return result.data[0]["id"]


def run_ingest(target_date: date) -> None:
    client = get_client()

    with job_context("ingest_races", "ingest", target_date) as ctx:
        race_ids = fetch_race_list(target_date)
        logger.info("Fetched %d race IDs", len(race_ids))
        total = 0

        for item in race_ids:
            nk_race_id: str = item["netkeiba_race_id"]
            detail = fetch_race_detail(nk_race_id)
            if not detail:
                continue

            # 競馬場
            rc_id = _ensure_racecourse(
                client,
                detail["racecourse_code"],
                detail["racecourse_name"],
                detail["racecourse_short"],
            )

            # レース upsert
            race_payload = {
                "external_race_code": nk_race_id,
                "racecourse_id": rc_id,
                "race_date": target_date.isoformat(),
                "race_number": detail["race_number"],
                "race_name": detail.get("race_name"),
                "track_type": detail.get("track_type") or "芝",
                "distance_m": detail.get("distance_m") or 0,
                "going": detail.get("going"),
                "field_size": detail.get("field_size"),
                "status": "scheduled",
                "data_source": "netkeiba",
            }

            result = (
                client.table("races")
                .upsert(
                    race_payload,
                    on_conflict="external_race_code",
                )
                .execute()
            )
            race_id: int = result.data[0]["id"]

            # オッズ取得
            odds_map = fetch_odds(nk_race_id)

            # 出走馬・エントリーupsert
            for entry in detail.get("entries", []):
                sex_age: str = entry.get("sex_age", "") or ""
                sex = sex_age[:1] if sex_age else None

                horse_id = _ensure_horse(
                    client,
                    entry.get("horse_external_code", ""),
                    entry.get("horse_name", "未登録"),
                    sex,
                )
                jockey_id = _ensure_person(
                    client, "jockeys",
                    entry.get("jockey_external_code", ""),
                    entry.get("jockey_name", "未登録"),
                ) if entry.get("jockey_external_code") else None
                trainer_id = _ensure_person(
                    client, "trainers",
                    entry.get("trainer_external_code", ""),
                    entry.get("trainer_name", "未登録"),
                ) if entry.get("trainer_external_code") else None

                odds_info = odds_map.get(entry["horse_number"], {})
                entry_payload = {
                    "race_id": race_id,
                    "horse_id": horse_id,
                    "horse_number": entry["horse_number"],
                    "bracket_number": entry.get("bracket_number"),
                    "sex_age": entry.get("sex_age"),
                    "declared_weight_kg": entry.get("declared_weight_kg"),
                    "declared_weight_diff_kg": entry.get("declared_weight_diff_kg"),
                    "latest_win_odds": odds_info.get("latest_win_odds"),
                    "morning_line_popularity": odds_info.get("morning_line_popularity"),
                    "scratch_flag": False,
                }
                if jockey_id:
                    entry_payload["jockey_id"] = jockey_id
                if trainer_id:
                    entry_payload["trainer_id"] = trainer_id

                client.table("race_entries").upsert(
                    entry_payload, on_conflict="race_id,horse_id"
                ).execute()

            total += 1
            logger.info("Processed race %s (%d entries)", nk_race_id, len(detail.get("entries", [])))

        ctx["records_processed"] = total
        logger.info("Ingest complete: %d races processed", total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="netkeibaからレースデータを取得する")
    parser.add_argument("--date", help="対象日 (YYYY-MM-DD, 省略時は本日)")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    run_ingest(target)

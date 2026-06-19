"""
JRA重賞成績データをDBに投入するジョブ。

Usage:
    python -m uma.ingest.jra_job --year 2026
    python -m uma.ingest.jra_job --year 2026 --limit 5   # 先頭5件のみ（テスト用）
    python -m uma.ingest.jra_job --year 2026 --source g1  # G1のみ
"""
import argparse
import logging
from datetime import datetime

from uma.db.client import get_client
from uma.ingest.jra import VENUE_CODE, VENUE_SHORT, fetch_jra_g1_index, fetch_jra_index, fetch_jra_result
from uma.jobs.base import job_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _ensure_racecourse(client, venue_name: str) -> int | None:
    code = VENUE_CODE.get(venue_name)
    if not code:
        logger.warning("Unknown venue: %s", venue_name)
        return None
    short = VENUE_SHORT.get(venue_name, venue_name[:1])
    result = (
        client.table("racecourses")
        .upsert(
            {"external_racecourse_code": code, "name": venue_name, "short_name": short, "is_active": True},
            on_conflict="external_racecourse_code",
        )
        .execute()
    )
    return result.data[0]["id"]


def _ensure_horse(client, horse_name: str) -> int:
    ext_code = f"jra_{horse_name}"
    result = (
        client.table("horses")
        .upsert({"external_horse_code": ext_code, "name": horse_name}, on_conflict="external_horse_code")
        .execute()
    )
    return result.data[0]["id"]


def _ensure_jockey(client, jockey_name: str) -> int:
    ext_code = f"jra_{jockey_name}"
    result = (
        client.table("jockeys")
        .upsert({"external_jockey_code": ext_code, "name": jockey_name}, on_conflict="external_jockey_code")
        .execute()
    )
    return result.data[0]["id"]


def run_jra_ingest(year: int, limit: int | None = None) -> None:
    client = get_client()

    with job_context("jra_ingest", "ingest") as ctx:
        races = fetch_jra_index(year)
        if limit:
            races = races[:limit]

        total = 0
        for race_info in races:
            path = race_info["path"]
            # external_race_code: "jra_2026_001" 形式
            ext_code = f"jra_{path.replace('/', '_').strip('_')}"
            ext_code = ext_code.replace("datafile_seiseki_replay_", "").replace(".html", "")

            result = fetch_jra_result(path)
            if not result:
                continue

            meta = result["meta"]
            entries = result["entries"]
            if not entries:
                logger.info("No entries for %s, skipping", path)
                continue

            # 競馬場
            venue = meta.get("venue") or race_info.get("venue", "")
            rc_id = _ensure_racecourse(client, venue)
            if not rc_id:
                continue

            # レース名: インデックスページの名前 (GⅠ/GⅡ/GⅢ付き) を優先
            # G1ページのh2はキャッチコピーになるためインデックス値を使う
            race_name = race_info.get("race_name") or meta.get("race_name")
            date_str = meta.get("date_str") or race_info.get("date_str")
            track_type = meta.get("track_type") or race_info.get("track_type", "芝")
            distance_m = meta.get("distance_m") or race_info.get("distance_m")

            if not date_str:
                logger.warning("No date for %s, skipping", path)
                continue

            # races upsert
            race_payload = {
                "external_race_code": ext_code,
                "racecourse_id": rc_id,
                "race_date": date_str,
                "race_name": race_name,
                "track_type": track_type,
                "distance_m": distance_m,
                "going": meta.get("going"),
                "field_size": len(entries),
                "status": "result_fixed",
                "data_source": "jra",
            }
            # race_number は重賞ページでは不明なため省略（nullable）
            race_result = (
                client.table("races")
                .upsert(race_payload, on_conflict="external_race_code")
                .execute()
            )
            race_id: int = race_result.data[0]["id"]

            # race_results upsert
            client.table("race_results").upsert(
                {
                    "race_id": race_id,
                    "result_fixed_at": datetime.now().isoformat(),
                    "winning_time": entries[0].get("finish_time") if entries else None,
                    "lap_text": meta.get("lap_text"),
                    "weather_final": meta.get("weather"),
                    "going_final": meta.get("going"),
                },
                on_conflict="race_id",
            ).execute()

            # 各出走馬
            for entry in entries:
                horse_id = _ensure_horse(client, entry["horse_name"])
                jockey_id = _ensure_jockey(client, entry["jockey_name"]) if entry.get("jockey_name") else None

                entry_payload = {
                    "race_id": race_id,
                    "horse_id": horse_id,
                    "horse_number": entry["horse_number"],
                    "bracket_number": entry.get("bracket_number"),
                    "sex_age": entry.get("sex_age"),
                    "declared_weight_kg": entry.get("declared_weight_kg"),
                    "declared_weight_diff_kg": entry.get("declared_weight_diff_kg"),
                    "scratch_flag": entry.get("abnormal_result_code") in ("取消", "除外"),
                }
                if jockey_id:
                    entry_payload["jockey_id"] = jockey_id

                entry_result = (
                    client.table("race_entries")
                    .upsert(entry_payload, on_conflict="race_id,horse_id")
                    .execute()
                )
                entry_id: int = entry_result.data[0]["id"]

                # entry_results upsert
                client.table("entry_results").upsert(
                    {
                        "race_entry_id": entry_id,
                        "finish_position": entry.get("finish_position"),
                        "finish_time": entry.get("finish_time"),
                        "margin_text": entry.get("margin_text"),
                        "passing_order_text": entry.get("passing_order_text"),
                        "last3f": entry.get("last3f"),
                        "abnormal_result_code": entry.get("abnormal_result_code"),
                        "dead_heat_flag": False,
                    },
                    on_conflict="race_entry_id",
                ).execute()

            total += 1
            logger.info("Stored %s: %s (%d entries)", date_str, race_name, len(entries))

        ctx["records_processed"] = total
        logger.info("JRA ingest complete: %d races stored", total)


def run_jra_g1_ingest(year: int, limit: int | None = None) -> None:
    """g1.html から GⅠレースのみを取得してDBに投入する。既存レコードは grade を更新する。"""
    client = get_client()

    with job_context("jra_g1_ingest", "ingest") as ctx:
        races = fetch_jra_g1_index(year)
        if limit:
            races = races[:limit]

        total = 0
        for race_info in races:
            path = race_info["path"]
            ext_code = f"jra_{path.replace('/', '_').strip('_')}"
            ext_code = ext_code.replace("datafile_seiseki_replay_", "").replace(".html", "")

            result = fetch_jra_result(path)
            if not result:
                continue

            meta = result["meta"]
            entries = result["entries"]
            if not entries:
                logger.info("No entries for %s, skipping", path)
                continue

            venue = meta.get("venue") or race_info.get("venue", "")
            rc_id = _ensure_racecourse(client, venue)
            if not rc_id:
                continue

            race_name = race_info.get("race_name") or meta.get("race_name")
            date_str = meta.get("date_str") or race_info.get("date_str")
            track_type = meta.get("track_type") or race_info.get("track_type", "芝")
            distance_m = meta.get("distance_m") or race_info.get("distance_m")
            grade = race_info.get("grade")

            if not date_str:
                logger.warning("No date for %s, skipping", path)
                continue

            race_payload = {
                "external_race_code": ext_code,
                "racecourse_id": rc_id,
                "race_date": date_str,
                "race_name": race_name,
                "track_type": track_type,
                "distance_m": distance_m,
                "grade": grade,
                "going": meta.get("going"),
                "field_size": len(entries),
                "status": "result_fixed",
                "data_source": "jra",
            }
            race_result = (
                client.table("races")
                .upsert(race_payload, on_conflict="external_race_code")
                .execute()
            )
            race_id: int = race_result.data[0]["id"]

            client.table("race_results").upsert(
                {
                    "race_id": race_id,
                    "result_fixed_at": datetime.now().isoformat(),
                    "winning_time": entries[0].get("finish_time") if entries else None,
                    "lap_text": meta.get("lap_text"),
                    "weather_final": meta.get("weather"),
                    "going_final": meta.get("going"),
                },
                on_conflict="race_id",
            ).execute()

            for entry in entries:
                horse_id = _ensure_horse(client, entry["horse_name"])
                jockey_id = _ensure_jockey(client, entry["jockey_name"]) if entry.get("jockey_name") else None

                entry_payload = {
                    "race_id": race_id,
                    "horse_id": horse_id,
                    "horse_number": entry["horse_number"],
                    "bracket_number": entry.get("bracket_number"),
                    "sex_age": entry.get("sex_age"),
                    "declared_weight_kg": entry.get("declared_weight_kg"),
                    "declared_weight_diff_kg": entry.get("declared_weight_diff_kg"),
                    "scratch_flag": entry.get("abnormal_result_code") in ("取消", "除外"),
                }
                if jockey_id:
                    entry_payload["jockey_id"] = jockey_id

                entry_result = (
                    client.table("race_entries")
                    .upsert(entry_payload, on_conflict="race_id,horse_id")
                    .execute()
                )
                entry_id: int = entry_result.data[0]["id"]

                client.table("entry_results").upsert(
                    {
                        "race_entry_id": entry_id,
                        "finish_position": entry.get("finish_position"),
                        "finish_time": entry.get("finish_time"),
                        "margin_text": entry.get("margin_text"),
                        "passing_order_text": entry.get("passing_order_text"),
                        "last3f": entry.get("last3f"),
                        "abnormal_result_code": entry.get("abnormal_result_code"),
                        "dead_heat_flag": False,
                    },
                    on_conflict="race_entry_id",
                ).execute()

            total += 1
            logger.info("Stored G1 %s: %s (%d entries)", date_str, race_name, len(entries))

        ctx["records_processed"] = total
        logger.info("JRA G1 ingest complete: %d races stored", total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JRA重賞成績データを取得してDBに投入する")
    parser.add_argument("--year", type=int, default=2026, help="対象年 (default: 2026)")
    parser.add_argument("--limit", type=int, default=None, help="取得件数上限（テスト用）")
    parser.add_argument("--source", choices=["jyusyo", "g1"], default="jyusyo", help="取得元 (default: jyusyo)")
    args = parser.parse_args()
    if args.source == "g1":
        run_jra_g1_ingest(args.year, args.limit)
    else:
        run_jra_ingest(args.year, args.limit)

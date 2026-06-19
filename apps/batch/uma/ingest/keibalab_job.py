"""
競馬ラボから過去レースデータを取得してDBに投入するジョブ（並列版）。

並列化戦略:
  - ThreadPoolExecutor でN日分の日付ページ取得を並列処理
  - スレッドごとに独立したHTTPセッション＋レート制限 (1.0s/thread)
  - 1レースの DB 書き込みをバッチ upsert に集約（~90 API呼び出し → ~7）

Usage:
    python -m uma.ingest.keibalab_job --date 20260614
    python -m uma.ingest.keibalab_job --from 20260104 --to 20260614
    python -m uma.ingest.keibalab_job --year 2026
    python -m uma.ingest.keibalab_job --year 2026 --workers 4
"""
import argparse
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

from uma.db.client import get_client
from uma.ingest.keibalab import (
    VENUE_MAP,
    HorseEntry,
    RaceMeta,
    fetch_date_races,
    fetch_race_full,
)
from uma.jobs.base import job_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

VENUE_TO_RC_CODE: dict[str, str] = {
    "01": "01", "02": "02", "03": "03", "04": "04",
    "05": "05", "06": "06", "07": "07", "08": "08",
    "09": "09", "10": "10",
}
VENUE_SHORT: dict[str, str] = {
    "01": "札", "02": "函", "03": "福", "04": "新",
    "05": "東", "06": "中山", "07": "中京", "08": "京",
    "09": "阪", "10": "小",
}

# DB 書き込みはスレッドセーフだが Supabase REST は HTTP (httpx.Client) なので
# 一つのクライアントをスレッド間共有しても問題なし（httpx は thread-safe）
_client_lock = threading.Lock()
_shared_client = None


def _get_client():
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                _shared_client = get_client()
    return _shared_client


# ──────────────────────────────────────────
#  マスタ upsert ヘルパー（バッチ対応）
# ──────────────────────────────────────────

def _upsert_racecourse(client, venue_code: str) -> int | None:
    rc_code = VENUE_TO_RC_CODE.get(venue_code)
    if not rc_code:
        return None
    venue_name = VENUE_MAP.get(venue_code, venue_code)
    short = VENUE_SHORT.get(venue_code, venue_name[:1])
    r = client.table("racecourses").upsert(
        {"external_racecourse_code": rc_code, "name": venue_name, "short_name": short, "is_active": True},
        on_conflict="external_racecourse_code",
    ).execute()
    return r.data[0]["id"]


def _batch_upsert_horses(client, entries: list[HorseEntry]) -> dict[str, int]:
    """entries の全馬を一括 upsert し {external_horse_code: id} を返す。"""
    payloads: list[dict] = []
    seen: set[str] = set()
    for e in entries:
        ext = f"kb_{e.horse_id}" if e.horse_id else f"kb_name_{e.horse_name}"
        if ext in seen:
            continue
        seen.add(ext)
        payload: dict = {"external_horse_code": ext, "name": e.horse_name}
        if e.sex_age:
            payload["sex"] = e.sex_age[:1]
        payloads.append(payload)

    if not payloads:
        return {}
    r = client.table("horses").upsert(payloads, on_conflict="external_horse_code").execute()
    return {row["external_horse_code"]: row["id"] for row in r.data}


def _batch_upsert_jockeys(client, entries: list[HorseEntry]) -> dict[str, int]:
    payloads: list[dict] = []
    seen: set[str] = set()
    for e in entries:
        if not e.jockey_name:
            continue
        ext = f"kb_{e.jockey_id}" if e.jockey_id else f"kb_name_{e.jockey_name}"
        if ext in seen:
            continue
        seen.add(ext)
        payloads.append({"external_jockey_code": ext, "name": e.jockey_name})

    if not payloads:
        return {}
    r = client.table("jockeys").upsert(payloads, on_conflict="external_jockey_code").execute()
    return {row["external_jockey_code"]: row["id"] for row in r.data}


def _batch_upsert_trainers(client, entries: list[HorseEntry]) -> dict[str, int]:
    payloads: list[dict] = []
    seen: set[str] = set()
    for e in entries:
        if not e.trainer_name:
            continue
        ext = f"kb_{e.trainer_id}" if e.trainer_id else f"kb_name_{e.trainer_name}"
        if ext in seen:
            continue
        seen.add(ext)
        p: dict = {"external_trainer_code": ext, "name": e.trainer_name}
        if e.trainer_affiliation:
            p["affiliation"] = e.trainer_affiliation
        payloads.append(p)

    if not payloads:
        return {}
    r = client.table("trainers").upsert(payloads, on_conflict="external_trainer_code").execute()
    return {row["external_trainer_code"]: row["id"] for row in r.data}


# ──────────────────────────────────────────
#  レース1件の DB 保存（バッチ書き込み）
# ──────────────────────────────────────────

def _store_race(client, meta: RaceMeta, entries: list[HorseEntry]) -> int | None:
    if not meta.distance_m:
        logger.warning("Skipping %s: no distance info", meta.race_id)
        return None

    rc_id = _upsert_racecourse(client, meta.venue_code)
    if not rc_id:
        logger.warning("Unknown venue_code %s, skipping %s", meta.venue_code, meta.race_id)
        return None

    race_date = f"{meta.date_str[:4]}-{meta.date_str[4:6]}-{meta.date_str[6:]}"
    ext_code = f"kb_{meta.race_id}"
    scheduled_start_at = f"{race_date}T{meta.start_time}:00+09:00" if meta.start_time else None
    has_results = any(e.finish_position for e in entries)

    race_payload: dict = {
        "external_race_code": ext_code,
        "racecourse_id": rc_id,
        "race_date": race_date,
        "race_number": meta.race_number,
        "race_name": meta.race_name or meta.race_class or f"{meta.venue_name}{meta.race_number}R",
        "class_name": meta.race_class or None,
        "track_type": meta.track_type or "芝",
        "distance_m": meta.distance_m,
        "weather": meta.weather or None,
        "going": meta.going or None,
        "scheduled_start_at": scheduled_start_at,
        "field_size": meta.field_size or len(entries),
        "status": "result_fixed" if has_results else "scheduled",
        "data_source": "keibalab",
        "weight_type": meta.weight_type or None,
        "prize_money_1st": meta.prize_money_1st or None,
    }
    if meta.grade:
        race_payload["grade"] = meta.grade

    race_r = client.table("races").upsert(race_payload, on_conflict="external_race_code").execute()
    race_id: int = race_r.data[0]["id"]

    # race_results
    if has_results:
        winner = next((e for e in entries if e.finish_position == 1), None)
        client.table("race_results").upsert(
            {
                "race_id": race_id,
                "result_fixed_at": datetime.now().isoformat(),
                "winning_time": winner.finish_time if winner else None,
                "weather_final": meta.weather or None,
                "going_final": meta.going or None,
            },
            on_conflict="race_id",
        ).execute()

    if not entries:
        return race_id

    # ── バッチ upsert: horses / jockeys / trainers ──
    horse_id_by_code = _batch_upsert_horses(client, entries)
    jockey_id_by_code = _batch_upsert_jockeys(client, entries)
    trainer_id_by_code = _batch_upsert_trainers(client, entries)

    # ── バッチ upsert: race_entries ──
    entry_payloads: list[dict] = []
    for e in entries:
        horse_ext = f"kb_{e.horse_id}" if e.horse_id else f"kb_name_{e.horse_name}"
        jockey_ext = f"kb_{e.jockey_id}" if e.jockey_id else f"kb_name_{e.jockey_name}"
        trainer_ext = f"kb_{e.trainer_id}" if e.trainer_id else f"kb_name_{e.trainer_name}"

        p: dict = {
            "race_id": race_id,
            "horse_id": horse_id_by_code.get(horse_ext),
            "horse_number": e.horse_number,
            "bracket_number": e.bracket_number,
            "sex_age": e.sex_age or None,
            "carried_weight": e.weight_carried,
            "declared_weight_kg": e.declared_weight_kg,
            "declared_weight_diff_kg": e.weight_diff,
            "latest_win_odds": e.win_odds,
            "scratch_flag": e.abnormal in ("取消", "除外"),
        }
        if e.jockey_name and jockey_ext in jockey_id_by_code:
            p["jockey_id"] = jockey_id_by_code[jockey_ext]
        if e.trainer_name and trainer_ext in trainer_id_by_code:
            p["trainer_id"] = trainer_id_by_code[trainer_ext]

        if p["horse_id"] is not None:
            entry_payloads.append(p)

    entry_r = client.table("race_entries").upsert(entry_payloads, on_conflict="race_id,horse_number").execute()
    entry_id_by_horsenum: dict[int, int] = {row["horse_number"]: row["id"] for row in entry_r.data}

    # ── バッチ upsert: entry_results ──
    result_payloads: list[dict] = []
    for e in entries:
        if not (e.finish_position or e.popularity or e.finish_time):
            continue
        eid = entry_id_by_horsenum.get(e.horse_number)
        if not eid:
            continue
        result_payloads.append({
            "race_entry_id": eid,
            "finish_position": e.finish_position,
            "finish_time": e.finish_time or None,
            "margin_text": e.margin or None,
            "passing_order_text": e.corner_positions or None,
            "last3f": e.last3f,
            "abnormal_result_code": e.abnormal or None,
            "popularity_final": e.popularity,
            "dead_heat_flag": False,
        })

    if result_payloads:
        client.table("entry_results").upsert(result_payloads, on_conflict="race_entry_id").execute()

    return race_id


# ──────────────────────────────────────────
#  日付単位の処理（スレッドから呼ばれる）
# ──────────────────────────────────────────

def _process_date(date_str: str, skip_ids: set[str]) -> list[str]:
    """
    指定日の全レースを取得・保存する。
    成功した race_id リストを返す（進捗共有用）。
    skip_ids はスレッドセーフに READ ONLY で参照する。
    """
    client = _get_client()
    stored_ids: list[str] = []

    try:
        race_summaries = fetch_date_races(date_str)
    except Exception as e:
        logger.error("Failed to fetch date page %s: %s", date_str, e)
        return stored_ids

    if not race_summaries:
        return stored_ids

    for summary in race_summaries:
        race_id = summary["race_id"]
        if race_id in skip_ids:
            continue

        try:
            meta, entries = fetch_race_full(race_id)
            if not meta:
                continue

            # date_page の情報でフォールバック補完
            if not meta.track_type:
                meta.track_type = summary.get("track_type", "芝")
            if not meta.distance_m:
                meta.distance_m = summary.get("distance_m")
            if not meta.field_size and summary.get("field_size"):
                meta.field_size = summary["field_size"]
            if not meta.weather and summary.get("weather"):
                meta.weather = summary["weather"]
            if not meta.going and summary.get("going_shiba"):
                meta.going = summary["going_shiba"]

            db_race_id = _store_race(client, meta, entries)
            if db_race_id:
                stored_ids.append(race_id)
                logger.info(
                    "[%s] %s%sR %s (%d頭)",
                    date_str, meta.venue_name, meta.race_number,
                    meta.race_name or meta.race_class, len(entries),
                )
        except Exception as e:
            logger.error("Error storing %s: %s", race_id, e, exc_info=True)

    return stored_ids


def _get_ingested_race_ids(client) -> set[str]:
    r = (
        client.table("races")
        .select("external_race_code")
        .eq("data_source", "keibalab")
        .execute()
    )
    result: set[str] = set()
    for row in r.data:
        code = row["external_race_code"]
        if code.startswith("kb_"):
            result.add(code[3:])
    return result


# ──────────────────────────────────────────
#  メイン ingest ジョブ
# ──────────────────────────────────────────

def run_keibalab_ingest(date_from: str, date_to: str, workers: int = 3) -> None:
    client = _get_client()

    d_from = date(int(date_from[:4]), int(date_from[4:6]), int(date_from[6:]))
    d_to = date(int(date_to[:4]), int(date_to[4:6]), int(date_to[6:]))

    with job_context("keibalab_ingest", "ingest") as ctx:
        logger.info("Loading already-ingested race IDs from DB...")
        # skip_ids はメインスレッドで構築後、ワーカーから READ ONLY 参照
        skip_ids: set[str] = _get_ingested_race_ids(client)
        logger.info("Found %d already-ingested races", len(skip_ids))

        # 対象日付リスト
        date_list: list[str] = []
        cur = d_from
        while cur <= d_to:
            date_list.append(cur.strftime("%Y%m%d"))
            cur += timedelta(days=1)

        logger.info(
            "Processing %d dates from %s to %s with %d workers",
            len(date_list), date_from, date_to, workers,
        )

        total_stored = 0
        # skip_ids を共有フォールスルー用 set として使用（スレッド間で extend）
        skip_ids_lock = threading.Lock()

        def process_date_safe(date_str: str) -> int:
            ids = _process_date(date_str, skip_ids)
            if ids:
                with skip_ids_lock:
                    skip_ids.update(ids)
            return len(ids)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_date_safe, ds): ds for ds in date_list}
            for future in as_completed(futures):
                ds = futures[future]
                try:
                    count = future.result()
                    total_stored += count
                    if count:
                        logger.info("Date %s done: %d races stored", ds, count)
                except Exception as e:
                    logger.error("Date %s failed: %s", ds, e)

        ctx["records_processed"] = total_stored
        logger.info("keibalab ingest complete: %d races stored", total_stored)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="競馬ラボから過去レースデータをDBに投入する（並列版）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", metavar="YYYYMMDD", help="特定日のみ取得")
    group.add_argument("--from", dest="date_from", metavar="YYYYMMDD", help="開始日")
    group.add_argument("--year", type=int, help="指定年の全レース")
    parser.add_argument("--to", dest="date_to", metavar="YYYYMMDD", help="終了日 (--from と組み合わせ)")
    parser.add_argument("--workers", type=int, default=3, help="並列スレッド数 (default: 3)")
    args = parser.parse_args()

    if args.date:
        run_keibalab_ingest(args.date, args.date, workers=1)
    elif args.year:
        d_from = f"{args.year}0104"
        d_to = date.today().strftime("%Y%m%d")
        run_keibalab_ingest(d_from, d_to, workers=args.workers)
    else:
        d_to = args.date_to or date.today().strftime("%Y%m%d")
        run_keibalab_ingest(args.date_from, d_to, workers=args.workers)

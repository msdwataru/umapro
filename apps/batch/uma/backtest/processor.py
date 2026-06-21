"""
バックテスト処理エンジン。

queued 状態の backtest_runs を取得し、model_predictions × entry_results を結合して
単勝（WIN）の回収率・的中率を計算し、backtest_bets / backtest_results に書き込む。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from uma.db.client import paginate

logger = logging.getLogger(__name__)

STAKE_PER_BET = 100  # 1 賭けあたり賭け金（円）


def _get_win_bet_type_id(client: Client) -> int:
    row = client.table("bet_types").select("id").eq("code", "WIN").single().execute()
    return row.data["id"]


def _fetch_predictions(client: Client, params: dict[str, Any]) -> list[dict]:
    """バックテストパラメータに合致する model_predictions を取得する。"""
    track_type: str | None = params.get("track_type") or None
    distance_min: int = int(params.get("distance_min") or 0)
    distance_max: int = int(params.get("distance_max") or 99999)
    ev_threshold: float = float(params.get("ev_threshold") or 0.0)
    date_from: str | None = params.get("date_from") or None
    date_to: str | None = params.get("date_to") or None
    model_version_id: int | None = params.get("model_version_id") or None
    max_rank: int | None = params.get("max_rank") or None

    def _make_query(off: int, lim: int):
        q = (
            client.table("model_predictions")
            .select(
                "id, race_entry_id, edge_value, predicted_value, prediction_rank,"
                "race_entries("
                "  id, race_id, horse_number, latest_win_odds,"
                "  races(id, race_date, track_type, distance_m, status),"
                "  entry_results(finish_position, abnormal_result_code)"
                ")"
            )
            .eq("prediction_target", "win")
            .gte("edge_value", ev_threshold)
        )
        if model_version_id is not None:
            q = q.eq("model_version_id", model_version_id)
        if max_rank is not None:
            q = q.lte("prediction_rank", max_rank)
        return q.range(off, off + lim - 1)

    rows = paginate(_make_query)

    # Python 側でフィルタ（Supabase の embedded filter が複雑なため）
    result = []
    for p in rows:
        entry = p.get("race_entries") or {}
        race = entry.get("races") or {}

        # 結果確定済みレースのみ
        if race.get("status") != "result_fixed":
            continue
        # コースフィルタ
        if track_type and race.get("track_type") != track_type:
            continue
        # 距離フィルタ
        d = race.get("distance_m") or 0
        if not (distance_min <= d <= distance_max):
            continue
        # 日付フィルタ
        rd = race.get("race_date") or ""
        if date_from and rd < date_from:
            continue
        if date_to and rd > date_to:
            continue

        result.append(p)

    return result


def _fetch_payouts(client: Client, race_ids: list[int], bet_type_id: int) -> dict[tuple[int, str], int]:
    """payouts テーブルから単勝払戻を取得。{(race_id, horse_number): payout_amount}"""
    if not race_ids:
        return {}

    result: dict[tuple[int, str], int] = {}
    batch_size = 200  # URL長制限対策: race_id を分割して取得
    for i in range(0, len(race_ids), batch_size):
        batch = race_ids[i:i + batch_size]
        rows = (
            client.table("payouts")
            .select("race_id, combination_key, payout_amount")
            .in_("race_id", batch)
            .eq("bet_type_id", bet_type_id)
            .execute()
        ).data
        for r in rows:
            result[(r["race_id"], r["combination_key"])] = r["payout_amount"]
    return result


def _calc_max_drawdown(cumulative_profits: list[float]) -> float:
    """累積損益リストから最大ドローダウン率を計算する。"""
    if not cumulative_profits:
        return 0.0
    peak = cumulative_profits[0]
    max_dd = 0.0
    for v in cumulative_profits:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    # ドローダウン率（cumulative に対して正規化）
    total_stake = len(cumulative_profits) * STAKE_PER_BET
    return max_dd / total_stake if total_stake > 0 else 0.0


def process_run(client: Client, run: dict) -> None:
    run_id: int = run["id"]
    params: dict = run["parameters_json"]
    logger.info("Processing backtest run %d: %s", run_id, params)

    # running に更新
    client.table("backtest_runs").update({
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", run_id).execute()

    try:
        win_bt_id = _get_win_bet_type_id(client)
        predictions = _fetch_predictions(client, params)
        logger.info("Matched %d predictions", len(predictions))

        # 対象 race_id 一覧 → payouts を一括取得
        race_ids = list({
            (p["race_entries"] or {}).get("races", {}).get("id")
            for p in predictions
            if (p.get("race_entries") or {}).get("races")
        })
        payout_map = _fetch_payouts(client, [rid for rid in race_ids if rid], win_bt_id)

        # backtest_bets を構築
        bet_payloads: list[dict] = []
        cumulative = 0.0
        cumulative_series: list[float] = []
        race_ids_seen: set[int] = set()

        for p in predictions:
            entry = p.get("race_entries") or {}
            race = entry.get("races") or {}
            er = entry.get("entry_results") or {}

            race_id: int | None = race.get("id")
            horse_number: int | None = entry.get("horse_number")
            finish_pos: int | None = er.get("finish_position")
            win_odds: float | None = entry.get("latest_win_odds")

            if race_id is None:
                continue

            is_hit = finish_pos == 1

            # 払戻: payouts テーブル優先、なければ odds で近似
            payout_raw = payout_map.get((race_id, str(horse_number))) if horse_number else None
            if payout_raw is not None:
                # payouts は 100円あたりの払戻金額
                payout = float(payout_raw)
            elif is_hit and win_odds:
                payout = round(float(win_odds) * STAKE_PER_BET, 2)
            else:
                payout = 0.0

            profit = payout - STAKE_PER_BET
            cumulative += profit
            cumulative_series.append(cumulative)
            race_ids_seen.add(race_id)

            bet_payloads.append({
                "backtest_run_id": run_id,
                "race_id": race_id,
                "race_entry_id": entry.get("id"),
                "bet_type_id": win_bt_id,
                "selection_key": str(horse_number) if horse_number else "",
                "stake_amount": STAKE_PER_BET,
                "payout_amount": payout,
                "is_hit": is_hit,
                "prediction_value": p.get("predicted_value"),
                "edge_value": p.get("edge_value"),
            })

        # backtest_bets を一括 insert（500件ずつ）
        for i in range(0, len(bet_payloads), 500):
            client.table("backtest_bets").insert(bet_payloads[i:i+500]).execute()
        logger.info("Inserted %d backtest_bets", len(bet_payloads))

        # 集計（WIN 単一式別）
        bet_count = len(bet_payloads)
        hit_count = sum(1 for b in bet_payloads if b["is_hit"])
        stake_total = bet_count * STAKE_PER_BET
        payout_total = sum(b["payout_amount"] for b in bet_payloads)
        roi = (payout_total - stake_total) / stake_total if stake_total > 0 else 0.0
        hit_rate = hit_count / bet_count if bet_count > 0 else 0.0
        max_dd = _calc_max_drawdown(cumulative_series)
        avg_odds = (
            sum(b["payout_amount"] / STAKE_PER_BET for b in bet_payloads if b["is_hit"]) / hit_count
            if hit_count > 0 else None
        )

        if bet_count > 0:
            client.table("backtest_results").insert({
                "backtest_run_id": run_id,
                "bet_type_id": win_bt_id,
                "race_count": len(race_ids_seen),
                "bet_count": bet_count,
                "hit_count": hit_count,
                "stake_amount": stake_total,
                "payout_amount": round(payout_total, 2),
                "roi": round(roi, 6),
                "hit_rate": round(hit_rate, 6),
                "max_drawdown": round(max_dd, 6),
                "avg_odds": round(avg_odds, 6) if avg_odds else None,
            }).execute()
            logger.info("Inserted backtest_results: ROI=%.1f%% hit=%.1f%% bets=%d",
                        roi * 100, hit_rate * 100, bet_count)

        client.table("backtest_runs").update({
            "status": "completed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        logger.info("Run %d completed", run_id)

    except Exception as exc:
        client.table("backtest_runs").update({
            "status": "failed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error_message": str(exc)[:1000],
        }).eq("id", run_id).execute()
        logger.exception("Run %d failed", run_id)
        raise

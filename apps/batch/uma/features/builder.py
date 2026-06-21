"""
特徴量生成モジュール。

全 race_entries × 過去成績（horse / jockey / trainer）× コース適性 を結合し、
LightGBM 学習用の DataFrame を生成する。

データリーク防止: 各エントリの特徴量は「そのレースの race_date より前」の
レコードのみから集計する（当日分は含まない）。

Usage:
    from uma.features.builder import FeatureBuilder

    builder = FeatureBuilder()
    df = builder.build(start_date="2026-01-01", end_date="2026-06-14")
    df = builder.add_odds_rank(df)
    df.to_parquet("race_features.parquet", index=False)

    # CLI
    python -m uma.features.builder --from-date 20260101 --to-date 20260614
"""

from __future__ import annotations

import argparse
import bisect
import logging
import math
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any

import pandas as pd

from uma.db.client import get_client, paginate

logger = logging.getLogger(__name__)

# ── エンコーディング定義 ─────────────────────────────────────────────
TRACK_ENC       = {"芝": 0, "ダート": 1, "障害": 2}
GOING_ENC       = {"良": 0, "稍重": 1, "重": 2, "不良": 3}
WEATHER_ENC     = {"晴": 0, "曇": 1, "雨": 2, "小雨": 2, "雪": 3, "小雪": 3}
WEIGHT_TYPE_ENC = {"馬齢": 0, "定量": 1, "ハンデ": 2, "別定": 3}
SEX_ENC         = {"牡": 0, "牝": 1, "騸": 2, "セ": 2}
JKY_AFF_ENC     = {"美": 0, "栗": 1, "地": 2, "外": 3}
TRN_AFF_ENC     = {"美": 0, "栗": 1, "地": 2}

# サンプル不足時のデフォルト値
_MIN_SAMPLES        = 3
_WIN_RATE_NEUTRAL   = 0.5
_AVG_FINISH_NEUTRAL = 7.0   # 平均的な出走頭数の半分程度
_LAST3F_NEUTRAL     = 36.0
_DAYS_NEUTRAL       = 60    # 初出走などの場合の前走間隔デフォルト


# ── ユーティリティ ─────────────────────────────────────────────────

def _dist_bucket(distance_m: int | None) -> int | None:
    if distance_m is None:
        return None
    return round(distance_m / 200) * 200


def _grade_enc(grade: str | None) -> int:
    if not grade:
        return 1
    if "GⅠ" in grade or "J・GⅠ" in grade:
        return 5
    if "GⅡ" in grade or "J・GⅡ" in grade:
        return 4
    if "GⅢ" in grade or "J・GⅢ" in grade:
        return 3
    return 2  # OP / Listed / 重賞以外はすべて2


def _parse_sex_age(sex_age: str | None) -> tuple[int, int]:
    """'牡3' → (sex_enc=0, age=3)"""
    if not sex_age:
        return 0, 0
    sex_enc = SEX_ENC.get(sex_age[0], 0)
    m = re.search(r"(\d+)", sex_age)
    age = int(m.group(1)) if m else 0
    return sex_enc, age


def _finish_time_to_sec(finish_time: str | None) -> float | None:
    """'1:34.5' → 94.5,  '34.5' → 34.5"""
    if not finish_time:
        return None
    m = re.match(r"(\d+):(\d+\.\d+)", finish_time)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m2 = re.match(r"(\d+\.\d+|\d+)", finish_time)
    return float(m2.group(1)) if m2 else None


def _safe_mean(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def _safe_std(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    mu = sum(vals) / len(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))


# ── 履歴インデックス ───────────────────────────────────────────────

class _History:
    """
    horse / jockey / trainer の過去成績を日付順に保持し、
    指定日付より前のレコードを O(log n) で取り出す。

    add() で全件追加後に sort() を呼ぶこと。
    """

    def __init__(self) -> None:
        self._dates: dict[int, list[str]] = defaultdict(list)
        self._data:  dict[int, list[dict]] = defaultdict(list)

    def add(self, entity_id: int, race_date: str, record: dict) -> None:
        self._dates[entity_id].append(race_date)
        self._data[entity_id].append(record)

    def sort(self) -> None:
        for eid in self._dates:
            pairs = sorted(zip(self._dates[eid], self._data[eid]), key=lambda x: x[0])
            self._dates[eid] = [p[0] for p in pairs]
            self._data[eid]  = [p[1] for p in pairs]

    def before(self, entity_id: int, race_date: str) -> list[dict]:
        """race_date より前（当日除く）の全レコードを返す。"""
        dates = self._dates.get(entity_id)
        if not dates:
            return []
        idx = bisect.bisect_left(dates, race_date)
        return self._data[entity_id][:idx]

    def last_n_before(self, entity_id: int, race_date: str, n: int) -> list[dict]:
        """race_date より前の直近 n 件を返す。"""
        return self.before(entity_id, race_date)[-n:]

    def __len__(self) -> int:
        return len(self._dates)


# ── 特徴量計算関数群 ────────────────────────────────────────────────

def _horse_features(
    horse_id: int,
    race_date: str,
    track_type: str | None,
    distance_m: int | None,
    hist: _History,
) -> dict:
    past  = hist.before(horse_id, race_date)
    n     = len(past)
    bucket = _dist_bucket(distance_m)

    # ── 通算成績 ──
    if n == 0:
        overall = {
            "horse_total_runs":    0,
            "horse_win_rate":      _WIN_RATE_NEUTRAL,
            "horse_rentai_rate":   _WIN_RATE_NEUTRAL,
            "horse_fukusho_rate":  _WIN_RATE_NEUTRAL,
            "horse_avg_finish":    _AVG_FINISH_NEUTRAL,
            "horse_avg_last3f":    _LAST3F_NEUTRAL,
        }
    else:
        positions = [r["finish_position"] for r in past if r.get("finish_position")]
        last3fs   = [r["last3f"] for r in past if r.get("last3f")]
        overall = {
            "horse_total_runs":   n,
            "horse_win_rate":     (sum(1 for p in positions if p == 1) / n
                                   if n >= _MIN_SAMPLES else _WIN_RATE_NEUTRAL),
            "horse_rentai_rate":  (sum(1 for p in positions if p <= 2) / n
                                   if n >= _MIN_SAMPLES else _WIN_RATE_NEUTRAL),
            "horse_fukusho_rate": (sum(1 for p in positions if p <= 3) / n
                                   if n >= _MIN_SAMPLES else _WIN_RATE_NEUTRAL),
            "horse_avg_finish":   _safe_mean(positions) or _AVG_FINISH_NEUTRAL,
            "horse_avg_last3f":   _safe_mean(last3fs)   or _LAST3F_NEUTRAL,
        }

    # ── 直近 5 / 3 走 ──
    last5 = hist.last_n_before(horse_id, race_date, 5)
    last3 = last5[-3:]
    l5_pos = [r["finish_position"] for r in last5 if r.get("finish_position")]
    l3_pos = [r["finish_position"] for r in last3 if r.get("finish_position")]
    l5_l3f = [r["last3f"] for r in last5 if r.get("last3f")]
    rolling = {
        "horse_last_finish":      (last5[-1]["finish_position"]
                                   if last5 and last5[-1].get("finish_position")
                                   else _AVG_FINISH_NEUTRAL),
        "horse_last3_avg_finish": _safe_mean(l3_pos) or _AVG_FINISH_NEUTRAL,
        "horse_last5_avg_finish": _safe_mean(l5_pos) or _AVG_FINISH_NEUTRAL,
        "horse_finish_std":       _safe_std(l5_pos)  or 0.0,
        "horse_last_last3f":      (last5[-1]["last3f"]
                                   if last5 and last5[-1].get("last3f")
                                   else _LAST3F_NEUTRAL),
    }

    # ── コース × 距離適性 ──
    def _win_rate_filtered(recs: list[dict]) -> float:
        nf = len(recs)
        if nf < _MIN_SAMPLES:
            return _WIN_RATE_NEUTRAL
        pos = [r["finish_position"] for r in recs if r.get("finish_position")]
        return sum(1 for p in pos if p == 1) / nf

    def _fukusho_rate_filtered(recs: list[dict]) -> float:
        nf = len(recs)
        if nf < _MIN_SAMPLES:
            return _WIN_RATE_NEUTRAL
        pos = [r["finish_position"] for r in recs if r.get("finish_position")]
        return sum(1 for p in pos if p <= 3) / nf

    course_past = [r for r in past if r.get("track_type") == track_type
                                    and r.get("dist_bucket") == bucket]
    dist_past   = [r for r in past if r.get("dist_bucket") == bucket]
    track_past  = [r for r in past if r.get("track_type") == track_type]

    course = {
        "horse_course_runs":          len(course_past),
        "horse_course_win_rate":      _win_rate_filtered(course_past),
        "horse_course_fukusho_rate":  _fukusho_rate_filtered(course_past),
        "horse_dist_bucket_win_rate": _win_rate_filtered(dist_past),
        "horse_track_type_win_rate":  _win_rate_filtered(track_past),
    }

    # ── 前走情報（直近 1 走） ──
    if last5:
        prev      = last5[-1]
        prev_date = prev.get("race_date", "")
        prev_dist = prev.get("distance_m")
        try:
            days = (date.fromisoformat(race_date) - date.fromisoformat(prev_date)).days
        except (ValueError, TypeError):
            days = _DAYS_NEUTRAL

        prev_feats = {
            "days_since_last_run": days,
            "distance_change":     (distance_m - prev_dist) if distance_m and prev_dist else 0,
            "prev_track_type_enc": TRACK_ENC.get(prev.get("track_type"), -1),
            "prev_going_enc":      GOING_ENC.get(prev.get("going"), -1),
            "prev_finish":         prev.get("finish_position") or _AVG_FINISH_NEUTRAL,
            "prev_last3f":         prev.get("last3f") or _LAST3F_NEUTRAL,
        }
    else:
        prev_feats = {
            "days_since_last_run": _DAYS_NEUTRAL,
            "distance_change":     0,
            "prev_track_type_enc": -1,
            "prev_going_enc":      -1,
            "prev_finish":         _AVG_FINISH_NEUTRAL,
            "prev_last3f":         _LAST3F_NEUTRAL,
        }

    return {**overall, **rolling, **course, **prev_feats}


def _jockey_features(
    jockey_id: int,
    race_date: str,
    track_type: str | None,
    bucket: int | None,
    hist: _History,
) -> dict:
    past = hist.before(jockey_id, race_date)
    n    = len(past)

    def _wr(recs: list[dict]) -> float:
        nf = len(recs)
        if nf < _MIN_SAMPLES:
            return _WIN_RATE_NEUTRAL
        pos = [r["finish_position"] for r in recs if r.get("finish_position")]
        return sum(1 for p in pos if p == 1) / nf

    positions = [r["finish_position"] for r in past if r.get("finish_position")]
    course_past = [r for r in past if r.get("track_type") == track_type
                                    and r.get("dist_bucket") == bucket]
    track_past  = [r for r in past if r.get("track_type") == track_type]

    return {
        "jockey_win_rate":         (_wr(past)),
        "jockey_rentai_rate":      (sum(1 for p in positions if p <= 2) / n
                                    if n >= _MIN_SAMPLES else _WIN_RATE_NEUTRAL),
        "jockey_fukusho_rate":     (sum(1 for p in positions if p <= 3) / n
                                    if n >= _MIN_SAMPLES else _WIN_RATE_NEUTRAL),
        "jockey_course_win_rate":  _wr(course_past),
        "jockey_track_win_rate":   _wr(track_past),
    }


def _trainer_features(
    trainer_id: int,
    race_date: str,
    hist: _History,
) -> dict:
    past = hist.before(trainer_id, race_date)
    n    = len(past)
    if n < _MIN_SAMPLES:
        return {
            "trainer_win_rate":     _WIN_RATE_NEUTRAL,
            "trainer_rentai_rate":  _WIN_RATE_NEUTRAL,
            "trainer_fukusho_rate": _WIN_RATE_NEUTRAL,
        }
    positions = [r["finish_position"] for r in past if r.get("finish_position")]
    return {
        "trainer_win_rate":     sum(1 for p in positions if p == 1) / n,
        "trainer_rentai_rate":  sum(1 for p in positions if p <= 2) / n,
        "trainer_fukusho_rate": sum(1 for p in positions if p <= 3) / n,
    }


# ── SC 正規化（レース内偏差値） ──────────────────────────────────────

_SC_COLS = [
    "horse_avg_finish",
    "horse_win_rate",
    "horse_course_win_rate",
    "jockey_win_rate",
    "trainer_win_rate",
    "carried_weight",
    "weight_diff",
    "age",
]


def _sc_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """各 race_id グループ内で _SC_COLS を z-score 標準化する。"""
    for col in _SC_COLS:
        if col not in df.columns:
            continue
        sc_values = pd.Series(0.0, index=df.index, dtype=float)
        for _, grp in df.groupby("race_id", sort=False):
            vals = grp[col].astype(float)
            rng = float(vals.max() - vals.min())
            if rng > 1e-9:  # 浮動小数点ノイズを除外
                mean = vals.mean()
                std = float(vals.std(ddof=0))
                sc_values.loc[grp.index] = ((vals - mean) / std).values
        df[f"{col}_sc"] = sc_values
    return df


# ── データロード ──────────────────────────────────────────────────────

def _load_all_results(client: Any) -> tuple[_History, _History, _History]:
    """
    全 entry_results を取得して horse / jockey / trainer の履歴インデックスを構築する。
    キーセットページネーション（race_entry_id 順）でオフセット方式のタイムアウトを回避する。
    """
    from uma.db.client import paginate_keyset
    logger.info("Loading all historical results (all-time)...")

    def _query(last_id, lim):
        q = (
            client.table("entry_results")
            .select(
                "race_entry_id, finish_position, last3f, "
                "race_entries("
                "  horse_id, jockey_id, trainer_id, "
                "  races(race_date, track_type, distance_m, going)"
                ")"
            )
            .filter("finish_position", "not.is", "null")
            .order("race_entry_id")
            .limit(lim)
        )
        if last_id is not None:
            q = q.gt("race_entry_id", last_id)
        return q

    rows = paginate_keyset(_query, keyset_col="race_entry_id")
    logger.info("Loaded %d historical entry_results", len(rows))

    horse_hist   = _History()
    jockey_hist  = _History()
    trainer_hist = _History()

    for r in rows:
        re_  = r.get("race_entries") or {}
        race = re_.get("races") or {}

        race_date  = race.get("race_date")
        if not race_date:
            continue

        track_type = race.get("track_type")
        distance_m = race.get("distance_m")
        going      = race.get("going")
        finish_pos = r.get("finish_position")
        last3f     = r.get("last3f")
        bucket     = _dist_bucket(distance_m)

        horse_id   = re_.get("horse_id")
        jockey_id  = re_.get("jockey_id")
        trainer_id = re_.get("trainer_id")

        if horse_id:
            horse_hist.add(horse_id, race_date, {
                "race_date":      race_date,
                "finish_position": finish_pos,
                "last3f":         last3f,
                "track_type":     track_type,
                "distance_m":     distance_m,
                "dist_bucket":    bucket,
                "going":          going,
            })

        if jockey_id:
            jockey_hist.add(jockey_id, race_date, {
                "race_date":      race_date,
                "finish_position": finish_pos,
                "track_type":     track_type,
                "dist_bucket":    bucket,
            })

        if trainer_id:
            trainer_hist.add(trainer_id, race_date, {
                "race_date":      race_date,
                "finish_position": finish_pos,
            })

    horse_hist.sort()
    jockey_hist.sort()
    trainer_hist.sort()

    logger.info(
        "History index built: %d horses, %d jockeys, %d trainers",
        len(horse_hist), len(jockey_hist), len(trainer_hist),
    )
    return horse_hist, jockey_hist, trainer_hist


def _load_target_entries(
    client: Any,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    """
    対象期間の race_entries を、関連テーブルをネストして全件取得する。
    latest_win_odds が NULL または scratch の馬は除外する。

    日付フィルタを Python 側でなく Supabase 側で行うため、
    先に races テーブルから対象 race_id を取得してから race_entries を絞り込む。
    全件取得→Python フィルタ方式はタイムアウトの原因になるため廃止。
    """
    logger.info("Loading target entries (start=%s end=%s)...", start_date, end_date)

    # Step1: 対象 race_id を races テーブルから取得（軽量クエリ）
    race_query = client.table("races").select("id")
    if start_date:
        race_query = race_query.gte("race_date", start_date)
    if end_date:
        race_query = race_query.lte("race_date", end_date)
    race_rows = paginate(lambda off, lim, q=race_query: q.range(off, off + lim - 1))
    race_ids = [r["id"] for r in race_rows]
    logger.info("Target races: %d (start=%s end=%s)", len(race_ids), start_date, end_date)

    if not race_ids:
        return []

    # Step2: race_id セットで race_entries を絞り込んでネスト取得
    # race_ids が多い場合はバッチ分割して IN 句の長さを制限する
    all_rows: list[dict] = []
    batch_size = 500
    for i in range(0, len(race_ids), batch_size):
        batch_ids = race_ids[i : i + batch_size]
        rows = paginate(lambda off, lim, ids=batch_ids: (
            client.table("race_entries")
            .select(
                "id, race_id, horse_id, jockey_id, trainer_id, "
                "bracket_number, horse_number, carried_weight, "
                "declared_weight_kg, declared_weight_diff_kg, "
                "latest_win_odds, blinkers_flag, sex_age, "
                "horses(sex, birth_date, sire_name, dam_name), "
                "jockeys(affiliation), "
                "trainers(affiliation), "
                "races("
                "  race_date, track_type, distance_m, weather, going, "
                "  field_size, grade, prize_money_1st, race_number, "
                "  weight_type, racecourse_id"
                "), "
                "entry_results(finish_position, last3f, finish_time)"
            )
            .eq("scratch_flag", False)
            .filter("latest_win_odds", "not.is", "null")
            .in_("race_id", ids)
            .range(off, off + lim - 1)
        ))
        all_rows.extend(rows)
        logger.info("  batch %d/%d → %d entries", i // batch_size + 1,
                    math.ceil(len(race_ids) / batch_size), len(all_rows))

    logger.info("Target entries: %d", len(all_rows))
    return all_rows


# ── メインビルダー ────────────────────────────────────────────────────

class FeatureBuilder:
    """
    指定日付範囲の全出走エントリから特徴量 DataFrame を生成する。

    出力 DataFrame の主なカラム:
        - race_entry_id, race_id, race_date  … 結合キー
        - finish_position                      … 学習ターゲット（結果確定済みのみ）
        - finish_time_sec                      … タイム予測ターゲット
        - 特徴量 ~60 カラム
        - {col}_sc                             … SC 標準化（レース内偏差値）

    Usage:
        builder = FeatureBuilder()
        df = builder.build("2026-01-01", "2026-06-14")
        df = builder.add_odds_rank(df)
        df.to_parquet("race_features.parquet", index=False)
    """

    def __init__(self) -> None:
        self.client = get_client()

    def build(
        self,
        start_date: str | None = None,
        end_date:   str | None = None,
    ) -> pd.DataFrame:
        horse_hist, jockey_hist, trainer_hist = _load_all_results(self.client)
        entries = _load_target_entries(self.client, start_date, end_date)

        if not entries:
            logger.warning("No entries found for the given date range.")
            return pd.DataFrame()

        rows = [
            self._build_row(e, horse_hist, jockey_hist, trainer_hist)
            for e in entries
        ]
        df = pd.DataFrame(rows)
        df = _sc_normalize(df)
        df = self.add_odds_rank(df)

        logger.info(
            "FeatureBuilder.build done: %d rows × %d cols", len(df), len(df.columns)
        )
        return df

    # ── 内部メソッド ──────────────────────────────────────────────────

    def _build_row(
        self,
        e: dict,
        horse_hist:   _History,
        jockey_hist:  _History,
        trainer_hist: _History,
    ) -> dict:
        race        = e.get("races") or {}
        horse_meta  = e.get("horses") or {}
        jockey_meta = e.get("jockeys") or {}
        trainer_meta = e.get("trainers") or {}

        # entry_results: PostgREST は 1:1 でも配列で返すことがある
        er_raw = e.get("entry_results")
        er = (er_raw[0] if isinstance(er_raw, list) and er_raw else
              er_raw if isinstance(er_raw, dict) else {}) or {}

        race_date  = race.get("race_date", "")
        track_type = race.get("track_type")
        distance_m = race.get("distance_m")
        bucket     = _dist_bucket(distance_m)

        horse_id   = e.get("horse_id")
        jockey_id  = e.get("jockey_id")
        trainer_id = e.get("trainer_id")
        sex_enc, age = _parse_sex_age(e.get("sex_age"))

        # 過去成績特徴量
        hf = (_horse_features(horse_id, race_date, track_type, distance_m, horse_hist)
              if horse_id else _horse_default_features())
        jf = (_jockey_features(jockey_id, race_date, track_type, bucket, jockey_hist)
              if jockey_id else _jockey_default_features())
        tf = (_trainer_features(trainer_id, race_date, trainer_hist)
              if trainer_id else _trainer_default_features())

        odds = float(e.get("latest_win_odds") or 1.0)

        return {
            # ── ID / メタ ──────────────────────────────────────────────
            "race_entry_id": e["id"],
            "race_id":       e.get("race_id"),
            "race_date":     race_date,

            # ── ターゲット（結果未確定なら None） ────────────────────────
            "finish_position":  er.get("finish_position"),
            "finish_time_sec":  _finish_time_to_sec(er.get("finish_time")),

            # ── レース条件 ─────────────────────────────────────────────
            "track_type_enc":       TRACK_ENC.get(track_type, -1),
            "distance_m":           distance_m,
            "dist_bucket":          bucket,
            "field_size":           race.get("field_size"),
            "grade_enc":            _grade_enc(race.get("grade")),
            "going_enc":            GOING_ENC.get(race.get("going"), -1),
            "weather_enc":          WEATHER_ENC.get(race.get("weather"), -1),
            "prize_money_1st_log":  math.log1p(race.get("prize_money_1st") or 0),
            "race_number":          race.get("race_number"),
            "weight_type_enc":      WEIGHT_TYPE_ENC.get(race.get("weight_type"), 0),
            "racecourse_id":        race.get("racecourse_id"),

            # ── エントリ静的情報 ───────────────────────────────────────
            "bracket_number":   e.get("bracket_number"),
            "horse_number":     e.get("horse_number"),
            "carried_weight":   float(e.get("carried_weight") or 55.0),
            "weight_kg":        e.get("declared_weight_kg"),
            "weight_diff":      e.get("declared_weight_diff_kg") or 0,
            "latest_win_odds":  odds,
            "odds_inv":         1.0 / odds,
            "blinkers_flag":    int(bool(e.get("blinkers_flag"))),
            "sex_enc":          sex_enc,
            "age":              age,

            # ── 血統（文字列のまま → LightGBM category として使用） ───────
            "sire_name": horse_meta.get("sire_name") or "",
            "dam_name":  horse_meta.get("dam_name") or "",

            # ── 属性エンコーディング ───────────────────────────────────
            "jockey_affiliation_enc":  JKY_AFF_ENC.get(jockey_meta.get("affiliation"), -1),
            "trainer_affiliation_enc": TRN_AFF_ENC.get(trainer_meta.get("affiliation"), -1),

            # ── 馬・騎手・調教師の過去成績 ─────────────────────────────
            **hf,
            **jf,
            **tf,
        }

    def add_odds_rank(self, df: pd.DataFrame) -> pd.DataFrame:
        """レース内人気順位を付与する（odds_inv 降順 = 1番人気 = 1）。"""
        if "race_id" in df.columns and "odds_inv" in df.columns:
            df["odds_rank"] = (
                df.groupby("race_id")["odds_inv"]
                .rank(ascending=False, method="min")
                .astype(int)
            )
        return df


# ── デフォルト特徴量（エンティティが不明の場合） ────────────────────────

def _horse_default_features() -> dict:
    return {
        "horse_total_runs": 0, "horse_win_rate": _WIN_RATE_NEUTRAL,
        "horse_rentai_rate": _WIN_RATE_NEUTRAL, "horse_fukusho_rate": _WIN_RATE_NEUTRAL,
        "horse_avg_finish": _AVG_FINISH_NEUTRAL, "horse_avg_last3f": _LAST3F_NEUTRAL,
        "horse_last_finish": _AVG_FINISH_NEUTRAL, "horse_last3_avg_finish": _AVG_FINISH_NEUTRAL,
        "horse_last5_avg_finish": _AVG_FINISH_NEUTRAL, "horse_finish_std": 0.0,
        "horse_last_last3f": _LAST3F_NEUTRAL,
        "horse_course_runs": 0, "horse_course_win_rate": _WIN_RATE_NEUTRAL,
        "horse_course_fukusho_rate": _WIN_RATE_NEUTRAL,
        "horse_dist_bucket_win_rate": _WIN_RATE_NEUTRAL,
        "horse_track_type_win_rate": _WIN_RATE_NEUTRAL,
        "days_since_last_run": _DAYS_NEUTRAL, "distance_change": 0,
        "prev_track_type_enc": -1, "prev_going_enc": -1,
        "prev_finish": _AVG_FINISH_NEUTRAL, "prev_last3f": _LAST3F_NEUTRAL,
    }


def _jockey_default_features() -> dict:
    return {
        "jockey_win_rate": _WIN_RATE_NEUTRAL, "jockey_rentai_rate": _WIN_RATE_NEUTRAL,
        "jockey_fukusho_rate": _WIN_RATE_NEUTRAL, "jockey_course_win_rate": _WIN_RATE_NEUTRAL,
        "jockey_track_win_rate": _WIN_RATE_NEUTRAL,
    }


def _trainer_default_features() -> dict:
    return {
        "trainer_win_rate": _WIN_RATE_NEUTRAL, "trainer_rentai_rate": _WIN_RATE_NEUTRAL,
        "trainer_fukusho_rate": _WIN_RATE_NEUTRAL,
    }


# ── CLI ──────────────────────────────────────────────────────────────

def _parse_date(s: str) -> str:
    return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="特徴量生成バッチ")
    parser.add_argument("--from-date", required=True, metavar="YYYYMMDD", help="開始日 (例: 20260101)")
    parser.add_argument("--to-date",   metavar="YYYYMMDD", help="終了日 (省略時=全期間)")
    parser.add_argument("--out", default="race_features.parquet", help="出力ファイルパス")
    args = parser.parse_args()

    start = _parse_date(args.from_date)
    end   = _parse_date(args.to_date) if args.to_date else None

    builder = FeatureBuilder()
    df = builder.build(start, end)

    if df.empty:
        print("No data.")
    else:
        df.to_parquet(args.out, index=False)
        print(f"Saved {len(df)} rows × {len(df.columns)} cols → {args.out}")
        print("\n特徴量一覧:")
        for col in sorted(df.columns):
            nn = df[col].notna().sum()
            print(f"  {col:<35} non-null={nn}/{len(df)}")

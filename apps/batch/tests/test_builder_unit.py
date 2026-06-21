"""builder.py の単体テスト（DB接続なし）"""
import sys
import unittest.mock as mock

sys.modules["supabase"] = mock.MagicMock()
sys.modules["uma.config"] = mock.MagicMock()

import pandas as pd
import pytest

from uma.features.builder import (
    _History,
    _dist_bucket,
    _finish_time_to_sec,
    _grade_enc,
    _horse_default_features,
    _horse_features,
    _parse_sex_age,
    _sc_normalize,
)


def test_dist_bucket():
    assert _dist_bucket(1600) == 1600
    assert _dist_bucket(1700) == 1600  # banker's rounding: round(8.5)=8
    assert _dist_bucket(1800) == 1800
    assert _dist_bucket(1900) == 2000  # round(9.5)=10
    assert _dist_bucket(None) is None


def test_grade_enc():
    assert _grade_enc("GⅠ") == 5
    assert _grade_enc("J・GⅠ") == 5
    assert _grade_enc("GⅡ") == 4
    assert _grade_enc("GⅢ") == 3
    assert _grade_enc(None) == 1


def test_parse_sex_age():
    assert _parse_sex_age("牡3") == (0, 3)
    assert _parse_sex_age("牝5") == (1, 5)
    assert _parse_sex_age("騸2") == (2, 2)
    assert _parse_sex_age(None) == (0, 0)


def test_finish_time_to_sec():
    assert _finish_time_to_sec("1:34.5") == 94.5
    assert _finish_time_to_sec("34.5") == 34.5
    assert _finish_time_to_sec(None) is None


def _make_history() -> _History:
    h = _History()
    h.add(1, "2026-01-10", {
        "finish_position": 1, "last3f": 34.5,
        "track_type": "芝", "distance_m": 1600, "dist_bucket": 1600,
        "going": "良", "race_date": "2026-01-10",
    })
    h.add(1, "2026-02-15", {
        "finish_position": 3, "last3f": 35.0,
        "track_type": "芝", "distance_m": 2000, "dist_bucket": 2000,
        "going": "稍重", "race_date": "2026-02-15",
    })
    h.add(1, "2026-03-20", {
        "finish_position": 2, "last3f": 34.8,
        "track_type": "ダート", "distance_m": 1400, "dist_bucket": 1400,
        "going": "良", "race_date": "2026-03-20",
    })
    h.sort()
    return h


def test_history_before():
    h = _make_history()
    assert len(h.before(1, "2026-03-20")) == 2   # 当日は含まない
    assert len(h.before(1, "2026-04-01")) == 3   # 全件
    assert h.before(999, "2026-06-01") == []     # 存在しない entity


def test_history_last_n_before():
    h = _make_history()
    assert len(h.last_n_before(1, "2026-04-01", 2)) == 2
    assert len(h.last_n_before(1, "2026-01-15", 5)) == 1


def test_horse_features_basic():
    h = _make_history()
    feats = _horse_features(1, "2026-04-01", "芝", 1600, h)

    assert feats["horse_total_runs"] == 3
    assert abs(feats["horse_win_rate"] - 1 / 3) < 1e-9

    # 芝×1600 は1件 < MIN_SAMPLES=3 → 中立値0.5
    assert feats["horse_course_win_rate"] == 0.5
    # 芝は2件 < 3 → 0.5
    assert feats["horse_track_type_win_rate"] == 0.5


def test_horse_features_prev():
    h = _make_history()
    feats = _horse_features(1, "2026-04-01", "芝", 1600, h)

    assert feats["prev_finish"] == 2         # 直近走は2着
    assert feats["prev_last3f"] == 34.8
    assert feats["prev_track_type_enc"] == 1  # ダート=1


def test_horse_features_new_horse():
    h = _make_history()
    feats = _horse_features(999, "2026-04-01", "芝", 1600, h)

    assert feats["horse_total_runs"] == 0
    assert feats["horse_win_rate"] == 0.5
    assert feats["days_since_last_run"] == 60   # _DAYS_NEUTRAL


def test_sc_normalize():
    df = pd.DataFrame({
        "race_id": [1, 1, 1, 2, 2],
        "horse_avg_finish": [3.0, 5.0, 7.0, 2.0, 8.0],
        "horse_win_rate": [0.3, 0.2, 0.5, 0.1, 0.4],
        "jockey_win_rate": [0.15, 0.12, 0.18, 0.20, 0.10],
        "trainer_win_rate": [0.10, 0.10, 0.10, 0.12, 0.12],
        "carried_weight": [55.0, 56.0, 54.0, 55.5, 54.5],
        "weight_diff": [2.0, -2.0, 0.0, 4.0, -4.0],
        "age": [3, 4, 5, 3, 4],
        "horse_course_win_rate": [0.3, 0.2, 0.5, 0.1, 0.4],
    })
    df_sc = _sc_normalize(df.copy())

    # SC カラムが追加されている
    assert "horse_avg_finish_sc" in df_sc.columns

    # レース内 SC の平均は 0
    sc_mean = df_sc[df_sc["race_id"] == 1]["horse_avg_finish_sc"].mean()
    assert abs(sc_mean) < 1e-9

    # 全員同値の場合は SC=0.0
    assert (df_sc[df_sc["race_id"] == 1]["trainer_win_rate_sc"] == 0.0).all()

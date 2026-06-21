"""
Phase0 Task 0-3: Walk-Forward 時系列分割の標準実装

ランダム分割は禁止。競馬は時系列であり、常に Expanding Window + Embargo を使う。
cv_splits.json を git 管理することで再現性を保証する。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

_CV_SPLITS_PATH = Path(__file__).parent.parent.parent / "cv_splits.json"

# 利用可能データが 2020年以降のため Train 開始は 2020
_DEFAULT_SPLITS: list[dict] = [
    {
        "fold": 1,
        "train_start": "2020-01-01",
        "train_end":   "2021-12-31",
        "embargo_start": "2022-01-01",
        "embargo_end":   "2022-01-14",
        "test_start":  "2022-01-15",
        "test_end":    "2022-12-31",
        "note": "Train=2020-2021, Test=2022",
    },
    {
        "fold": 2,
        "train_start": "2020-01-01",
        "train_end":   "2022-12-31",
        "embargo_start": "2023-01-01",
        "embargo_end":   "2023-01-14",
        "test_start":  "2023-01-15",
        "test_end":    "2023-12-31",
        "note": "Train=2020-2022, Test=2023",
    },
    {
        "fold": 3,
        "train_start": "2020-01-01",
        "train_end":   "2023-12-31",
        "embargo_start": "2024-01-01",
        "embargo_end":   "2024-01-14",
        "test_start":  "2024-01-15",
        "test_end":    "2024-12-31",
        "note": "Train=2020-2023, Test=2024",
    },
    {
        "fold": 4,
        "train_start": "2020-01-01",
        "train_end":   "2024-12-31",
        "embargo_start": "2025-01-01",
        "embargo_end":   "2025-01-14",
        "test_start":  "2025-01-15",
        "test_end":    "2025-12-31",
        "note": "Train=2020-2024, Test=2025",
    },
    {
        "fold": 5,
        "train_start": "2020-01-01",
        "train_end":   "2025-12-31",
        "embargo_start": "2026-01-01",
        "embargo_end":   "2026-01-14",
        "test_start":  "2026-01-15",
        "test_end":    "2026-12-31",
        "note": "Train=2020-2025, Test=2026(最終)",
    },
]


def load_cv_splits() -> list[dict]:
    """
    cv_splits.json から Fold 定義を読み込む。
    ファイルが存在しない場合はデフォルトを保存して返す。
    """
    if _CV_SPLITS_PATH.exists():
        with open(_CV_SPLITS_PATH, encoding="utf-8") as f:
            return json.load(f)
    save_cv_splits(_DEFAULT_SPLITS)
    return _DEFAULT_SPLITS


def save_cv_splits(splits: list[dict]) -> None:
    """Fold 定義を cv_splits.json に保存（git 管理対象）。"""
    _CV_SPLITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CV_SPLITS_PATH, "w", encoding="utf-8") as f:
        json.dump(splits, f, indent=2, ensure_ascii=False)


def iter_folds(
    df: pd.DataFrame,
    date_col: str = "race_date",
    splits: list[dict] | None = None,
) -> list[tuple[int, pd.DataFrame, pd.DataFrame]]:
    """
    Walk-Forward 分割イテレータ。

    Yields
    ------
    (fold_num, train_df, test_df)
        embargo 期間は train・test 両方から除外される。

    Notes
    -----
    ハイパーパラメータ調整は各 Fold の train_df 内で完結させること。
    test_df を見てチューニングすることは禁止。
    """
    if splits is None:
        splits = load_cv_splits()

    dates = pd.to_datetime(df[date_col])

    for fold in splits:
        train_mask = (dates >= fold["train_start"]) & (dates <= fold["train_end"])
        test_mask  = (dates >= fold["test_start"])  & (dates <= fold["test_end"])
        train_df   = df[train_mask].copy()
        test_df    = df[test_mask].copy()

        if len(train_df) == 0 or len(test_df) == 0:
            continue

        yield fold["fold"], train_df, test_df


def get_final_fold(
    df: pd.DataFrame,
    date_col: str = "race_date",
    splits: list[dict] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    最終評価用 (train, test)。最後の Fold のみ使用。
    最終報告値の算出専用。ハイパーパラメータ調整には使わない。
    """
    if splits is None:
        splits = load_cv_splits()
    last  = splits[-1]
    dates = pd.to_datetime(df[date_col])
    train = df[(dates >= last["train_start"]) & (dates <= last["train_end"])].copy()
    test  = df[(dates >= last["test_start"])  & (dates <= last["test_end"])].copy()
    return train, test

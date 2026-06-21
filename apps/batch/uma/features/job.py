"""
特徴量生成ジョブ。

過去データに対して特徴量 DataFrame を生成し、
- artifacts/ に parquet 保存
- feature_sets テーブルにメタデータ登録
- job_runs テーブルにジョブ実行記録

Usage:
    cd apps/batch
    python -m uma.features.job --from-date 20260101 --to-date 20260614
    python -m uma.features.job --from-date 20260101  # to-date 省略時 = 全期間
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

from uma.db.client import get_client
from uma.features.builder import FeatureBuilder
from uma.jobs.base import job_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_FEATURE_SET_NAME    = "lgbm_ranker_v1"
_FEATURE_SET_VERSION = "v1"
_ARTIFACTS_DIR       = Path(__file__).parent.parent.parent / "artifacts"


def _parse_date(s: str) -> str:
    return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")


def _ensure_feature_set(client, feature_schema: dict) -> int:
    result = (
        client.table("feature_sets")
        .upsert(
            {
                "feature_set_name": _FEATURE_SET_NAME,
                "version": _FEATURE_SET_VERSION,
                "description": (
                    "LightGBM Ranker 用特徴量セット。"
                    "馬・騎手・調教師の通算成績、コース適性、前走情報、SC標準化（レース内偏差値）を含む。"
                ),
                "feature_schema_json": feature_schema,
                "is_active": True,
            },
            on_conflict="feature_set_name,version",
        )
        .execute()
    )
    return result.data[0]["id"]


def main() -> None:
    parser = argparse.ArgumentParser(description="特徴量生成ジョブ")
    parser.add_argument("--from-date", required=True, metavar="YYYYMMDD", help="開始日")
    parser.add_argument("--to-date",   metavar="YYYYMMDD", help="終了日（省略時=全期間）")
    parser.add_argument("--out", help="出力parquetパス（省略時=artifacts/race_features_v1.parquet）")
    args = parser.parse_args()

    start_date = _parse_date(args.from_date)
    end_date   = _parse_date(args.to_date) if args.to_date else None

    _ARTIFACTS_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else _ARTIFACTS_DIR / "race_features_v1.parquet"

    client = get_client()

    with job_context("feature_build", "feature") as ctx:
        # ── 特徴量生成 ─────────────────────────────────────────
        builder = FeatureBuilder()
        df = builder.build(start_date=start_date, end_date=end_date)

        if df.empty:
            logger.warning("生成された特徴量が0件です")
            ctx["records_processed"] = 0
            return

        # ── parquet 保存 ──────────────────────────────────────
        df.to_parquet(out_path, index=False)
        logger.info("Saved parquet: %s (%d rows × %d cols)", out_path, len(df), len(df.columns))

        # ── feature_sets 登録 ─────────────────────────────────
        # finish_position が NULL のエントリも特徴量としては存在するため分けて計上
        labeled_rows   = int(df["finish_position"].notna().sum())
        unlabeled_rows = len(df) - labeled_rows

        feature_cols = [
            c for c in df.columns
            if c not in ("race_entry_id", "race_id", "race_date",
                         "finish_position", "finish_time_sec")
        ]
        feature_schema = {
            "features": sorted(feature_cols),
            "n_features": len(feature_cols),
            "rows_total": len(df),
            "rows_labeled": labeled_rows,
            "rows_unlabeled": unlabeled_rows,
            "date_range": {"start": start_date, "end": end_date or "all"},
            "parquet_path": str(out_path),
        }

        fs_id = _ensure_feature_set(client, feature_schema)
        logger.info(
            "feature_sets 登録完了: id=%d name=%s version=%s",
            fs_id, _FEATURE_SET_NAME, _FEATURE_SET_VERSION,
        )

        ctx["records_processed"] = len(df)

    # ── サマリ出力 ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"特徴量生成完了")
    print(f"  出力先   : {out_path}")
    print(f"  行数     : {len(df):,}  (ラベル付き={labeled_rows:,} / ラベルなし={unlabeled_rows:,})")
    print(f"  特徴量数 : {len(feature_cols)}")
    print(f"  期間     : {start_date} 〜 {end_date or '全期間'}")
    print(f"{'='*60}")
    print("\n特徴量サマリ:")

    # 数値カラムの基本統計
    num_cols = df[feature_cols].select_dtypes(include="number").columns.tolist()
    if num_cols:
        stats = df[num_cols].describe().T[["count", "mean", "std", "min", "max"]]
        for col, row in stats.iterrows():
            nn = int(row["count"])
            print(
                f"  {col:<40} "
                f"non-null={nn:>6}  "
                f"mean={row['mean']:>8.3f}  "
                f"std={row['std']:>7.3f}  "
                f"[{row['min']:.2f}, {row['max']:.2f}]"
            )


if __name__ == "__main__":
    main()

"""
過去レースの予測を一括生成するバックフィルジョブ。

Usage:
    cd apps/batch
    python -m uma.predictions.backfill_job --from-date 20260101 --to-date 20260619
    python -m uma.predictions.backfill_job --from-date 20260601 --model odds_drift
    python -m uma.predictions.backfill_job --from-date 20260601 --model place_odds
    python -m uma.predictions.backfill_job --from-date 20260601 --model course_form
"""

import argparse
import logging
from datetime import datetime

from uma.db.client import get_client
from uma.jobs.base import job_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_MODEL_MAP = {
    "rule_based":   "uma.predictions.rule_based",
    "place_odds":   "uma.predictions.place_odds_model",
    "odds_drift":   "uma.predictions.odds_drift_model",
    "course_form":  "uma.predictions.course_form_model",
    "lgbm_ranker":  "uma.predictions.lgbm_ranker",
}


def _parse_date(s: str) -> str:
    return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")


def _load_model(model_key: str):
    import importlib
    module_path = _MODEL_MAP[model_key]
    mod = importlib.import_module(module_path)
    return mod.ensure_feature_set, mod.ensure_model_version, mod.generate


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill predictions for past races")
    parser.add_argument("--from-date", required=True, metavar="YYYYMMDD", help="Start race_date (inclusive)")
    parser.add_argument("--to-date", metavar="YYYYMMDD", help="End race_date (inclusive, default: today)")
    parser.add_argument(
        "--model",
        default="rule_based",
        choices=list(_MODEL_MAP.keys()),
        help="使用する予測モデル (default: rule_based)",
    )
    args = parser.parse_args()

    start_date = _parse_date(args.from_date)
    end_date = _parse_date(args.to_date) if args.to_date else None

    ensure_feature_set, ensure_model_version, generate = _load_model(args.model)

    client = get_client()
    job_name = f"{args.model}_backfill"
    with job_context(job_name, "predict") as ctx:
        feature_set_id = ensure_feature_set(client)
        model_version_id = ensure_model_version(client, feature_set_id)
        count = generate(client, model_version_id, feature_set_id, start_date=start_date, end_date=end_date)
        ctx["records_processed"] = count


if __name__ == "__main__":
    main()

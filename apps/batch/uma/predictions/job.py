"""
ルールベース予測生成ジョブ。

Usage:
    cd apps/batch
    python -m uma.predictions.job
"""

import logging

from uma.db.client import get_client
from uma.jobs.base import job_context
from uma.predictions.rule_based import ensure_feature_set, ensure_model_version, generate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    client = get_client()
    with job_context("rule_based_predictions", "predict") as ctx:
        feature_set_id = ensure_feature_set(client)
        model_version_id = ensure_model_version(client, feature_set_id)
        count = generate(client, model_version_id, feature_set_id)
        ctx["records_processed"] = count


if __name__ == "__main__":
    main()

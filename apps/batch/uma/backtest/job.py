"""
バックテスト処理ジョブ。queued な backtest_runs を全て処理する。

Usage:
    cd apps/batch
    python -m uma.backtest.job
    python -m uma.backtest.job --run-id 2   # 特定の run だけ処理
"""

import argparse
import logging

from uma.db.client import get_client
from uma.backtest.processor import process_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued backtest runs")
    parser.add_argument("--run-id", type=int, help="特定の run_id だけ処理する")
    args = parser.parse_args()

    client = get_client()

    if args.run_id:
        rows = client.table("backtest_runs").select("*").eq("id", args.run_id).execute().data
    else:
        rows = (
            client.table("backtest_runs")
            .select("*")
            .eq("status", "queued")
            .order("created_at")
            .execute()
            .data
        )

    if not rows:
        logger.info("処理対象の backtest_runs がありません")
        return

    logger.info("%d 件の backtest_run を処理します", len(rows))
    for run in rows:
        process_run(client, run)


if __name__ == "__main__":
    main()

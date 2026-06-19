import logging
from contextlib import contextmanager
from datetime import date
from typing import Generator

from uma.db.client import get_client

logger = logging.getLogger(__name__)


@contextmanager
def job_context(
    job_name: str,
    job_type: str,
    target_date: date | None = None,
) -> Generator[dict, None, None]:
    """
    job_runs テーブルへ実行開始/完了/失敗を記録するコンテキストマネージャ。

    Usage:
        with job_context("ingest_races", "ingest", date.today()) as ctx:
            records = fetch_races()
            ctx["records_processed"] = len(records)
    """
    client = get_client()
    run_record: dict = {
        "job_name": job_name,
        "job_type": job_type,
        "status": "running",
        "target_date": target_date.isoformat() if target_date else None,
    }
    result = client.table("job_runs").insert(run_record).execute()
    run_id: int = result.data[0]["id"]
    logger.info("Job started: %s (id=%d)", job_name, run_id)

    ctx: dict = {"records_processed": 0}
    try:
        yield ctx
        client.table("job_runs").update(
            {
                "status": "success",
                "records_processed": ctx["records_processed"],
            }
        ).eq("id", run_id).execute()
        logger.info("Job succeeded: %s (id=%d, records=%d)", job_name, run_id, ctx["records_processed"])
    except Exception as exc:
        client.table("job_runs").update(
            {
                "status": "failed",
                "error_summary": str(exc)[:1000],
            }
        ).eq("id", run_id).execute()
        logger.exception("Job failed: %s (id=%d)", job_name, run_id)
        raise

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

from supabase import create_client, Client
from uma.config import config

logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000
_MAX_RETRIES = 5
_RETRY_BACKOFF = [5, 10, 20, 40, 60]  # 秒


@lru_cache(maxsize=1)
def get_client() -> Client:
    """service_role キーを使ったSupabaseクライアント（RLSをバイパス）"""
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def paginate(query_fn, page_size: int = _PAGE_SIZE) -> list[dict]:
    """
    Supabase のデフォルト1000行制限を回避するオフセットページネーション。
    statement timeout (57014) に対してリトライ＋指数バックオフを行う。

    Args:
        query_fn: (offset, limit) -> QueryBuilder を返す callable
        page_size: 1リクエストあたりの行数（デフォルト 1000）
    """
    rows: list[dict] = []
    offset = 0
    while True:
        batch = _fetch_with_retry(query_fn, offset, page_size)
        rows.extend(batch)
        logger.debug("paginate: offset=%d batch=%d total=%d", offset, len(batch), len(rows))
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def paginate_keyset(query_fn, keyset_col: str, page_size: int = _PAGE_SIZE) -> list[dict]:
    """
    キーセットページネーション（cursor-based）。
    オフセット方式と異なり深いページでも O(1) のコストで取得できる。

    Args:
        query_fn: (last_id, limit) -> QueryBuilder を返す callable
                  last_id=None の場合は先頭から取得
        keyset_col: ページングに使うカラム名（主キー想定）
        page_size: 1リクエストあたりの行数

    Example:
        rows = paginate_keyset(
            lambda last_id, lim: (
                client.table("entry_results")
                .select("race_entry_id, finish_position")
                .order("race_entry_id")
                .gt("race_entry_id", last_id) if last_id else
                client.table("entry_results")
                .select("race_entry_id, finish_position")
                .order("race_entry_id")
            ).limit(lim),
            keyset_col="race_entry_id",
        )
    """
    rows: list[dict] = []
    last_id = None
    while True:
        batch = _fetch_with_retry(lambda _off, lim, lid=last_id: query_fn(lid, lim), 0, page_size)
        rows.extend(batch)
        logger.debug("paginate_keyset: last_id=%s batch=%d total=%d", last_id, len(batch), len(rows))
        if len(batch) < page_size:
            break
        last_id = batch[-1][keyset_col]
    return rows


def _fetch_with_retry(query_fn, offset: int, page_size: int) -> list[dict]:
    """タイムアウト・一時エラーに対してリトライするフェッチ処理。"""
    from postgrest.exceptions import APIError  # 遅延インポート
    for attempt, wait in enumerate([0] + _RETRY_BACKOFF):
        if wait:
            logger.warning("paginate retry %d/%d in %ds (offset=%d)",
                           attempt, _MAX_RETRIES, wait, offset)
            time.sleep(wait)
        try:
            return query_fn(offset, page_size).execute().data
        except APIError as e:
            code = (e.args[0] or {}).get("code", "") if e.args else ""
            if code in ("57014", "57P01", "08006", "08001") and attempt < _MAX_RETRIES:
                continue  # タイムアウト／接続断 → リトライ
            raise
    return []  # unreachable

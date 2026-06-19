from typing import Any
from supabase import Client


def upsert_records(
    client: Client,
    table: str,
    records: list[dict[str, Any]],
    on_conflict: str,
) -> int:
    """テーブルへのupsertを実行し、処理件数を返す"""
    if not records:
        return 0
    result = (
        client.table(table)
        .upsert(records, on_conflict=on_conflict)
        .execute()
    )
    return len(result.data)

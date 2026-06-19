from unittest.mock import MagicMock, patch
from uma.db.upsert import upsert_records


def test_upsert_empty_returns_zero():
    client = MagicMock()
    result = upsert_records(client, "races", [], "external_race_code")
    assert result == 0
    client.table.assert_not_called()


def test_upsert_calls_table():
    client = MagicMock()
    client.table.return_value.upsert.return_value.execute.return_value.data = [{"id": 1}]
    count = upsert_records(client, "races", [{"external_race_code": "R001"}], "external_race_code")
    assert count == 1
    client.table.assert_called_once_with("races")

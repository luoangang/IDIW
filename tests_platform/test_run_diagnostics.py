import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore


def make_store():
    store = PlatformStore(SETTINGS)
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    store.connect = Mock(return_value=connection)
    return store, connection, cursor


def test_failed_result_keeps_per_source_warnings_in_existing_result_column():
    store, connection, cursor = make_store()
    cursor.rowcount = 1
    store.finalize_parent_for_package_run = Mock()
    result = {"status": "failed", "warnings": [{"code": "FEED_FAILED", "reason": "HTTP_ERROR", "message": "HTTP 503"}]}
    store.fail_package_run(1, "lease", "failed", "ALL_FEEDS_FAILED", "offline", 1,
                           Path("work"), Path("work/process.log"), result=result)
    sql, values = cursor.execute.call_args.args
    assert "result_json=%s" in sql
    assert json.loads(values[6]) == result
    connection.commit.assert_called_once()
    store.finalize_parent_for_package_run.assert_called_once_with(1)


def test_run_exposes_bounded_warnings_for_each_attempt():
    store, connection, cursor = make_store()
    cursor.fetchone.return_value = {"id": 1, "request_snapshot_json": '{"query":"AI"}'}
    cursor.fetchall.return_value = [{"id": 3, "attempt_no": 2, "warnings_json": json.dumps([{"code": "FEED_STATS"}] * 125)}]
    result = store.run(1)
    package = result["packages"][0]
    assert package["warning_count"] == 125
    assert len(package["warnings"]) == 100
    assert package["attempt_no"] == 2
    assert "warnings_json" not in package
    connection.close.assert_called_once()

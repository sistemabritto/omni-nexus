"""Contract tests for the read-only Growth Audit collector."""

from scripts.growth_audit import metric_value


def test_metric_value_preserves_unsupported_metrics() -> None:
    assert metric_value({"data": []}, "watch_time") == "NOT_SUPPORTED"


def test_metric_value_marks_api_failure_without_fabricating_zero() -> None:
    assert metric_value({"error": "permission"}, "reach") == "COLLECTION_FAILED"


def test_metric_value_reads_first_metric_value() -> None:
    payload = {"data": [{"name": "reach", "values": [{"value": 1234}]}]}
    assert metric_value(payload, "reach") == 1234


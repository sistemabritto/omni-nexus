import importlib.util
from pathlib import Path
from datetime import datetime

spec = importlib.util.spec_from_file_location("reels_producer", Path(__file__).resolve().parents[2] / "dashboard/backend/reels_producer.py")
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)


def fixture():
    return {"collected_at": "2026-09-12T12:00:00+00:00", "start_inclusive": "2026-08-13T00:00:00+00:00",
            "sources": {"instagram": {"status": "ok", "data": {"media": [
                {"id": "a", "media_product_type": "REELS", "timestamp": "2026-09-11T12:00:00+00:00"},
                {"id": "a", "media_product_type": "REELS", "timestamp": "2026-09-11T12:00:00+00:00"},
                {"id": "b", "media_product_type": "FEED", "timestamp": "2026-09-12T12:00:00+00:00"}]}}}}


def test_unique_reels_only():
    result = producer.publication_counts(fixture(), datetime(2026, 9, 12, 10, tzinfo=producer.BRT))
    assert result["cycle"] == 1
    assert result["today"] == 0


def test_missing_taxonomy_and_stale_are_unknown():
    data = fixture()
    del data["sources"]["instagram"]["data"]["media"][0]["media_product_type"]
    assert producer.publication_counts(data, datetime(2026, 9, 12, 10, tzinfo=producer.BRT)) is None
    assert producer.publication_counts(fixture(), datetime(2026, 9, 15, 10, tzinfo=producer.BRT)) is None


def test_failed_source_never_zero():
    data = fixture()
    data["sources"]["instagram"]["status"] = "error"
    assert producer.publication_counts(data, datetime(2026, 9, 12, 10, tzinfo=producer.BRT)) is None


def test_incomplete_pagination_is_unknown():
    data = fixture()
    data["sources"]["instagram"]["data"]["pagination_truncated"] = True
    assert producer.publication_counts(data, datetime(2026, 9, 12, 10, tzinfo=producer.BRT)) is None


def test_persistent_delivery_dedup_and_failure_retry(tmp_path, monkeypatch):
    import sys
    import types
    monkeypatch.setattr(producer, "REPORTS", tmp_path)
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 9, 12, 10, tzinfo=tz)
    monkeypatch.setattr(producer, "datetime", Clock)
    report = {"published": None, "issues": ["source unavailable"], "expected_before_today": 4,
              "pending_approvals_all_workflows": 0}
    monkeypatch.setattr(producer, "inspect", lambda now: report)
    calls = []
    notification = types.SimpleNamespace(send_telegram_alert=lambda text: calls.append(text) or False)
    monkeypatch.setitem(sys.modules, "notifications", notification)
    import pytest
    with pytest.raises(RuntimeError):
        producer.tick()
    assert not (tmp_path / "notification-state.json").exists()
    notification.send_telegram_alert = lambda text: calls.append(text) or True
    assert producer.tick()["sent"] is True
    assert producer.tick()["sent"] is False
    assert len(calls) == 2

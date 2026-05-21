import time

from frigate_protect_events.coalesce import CoalesceTracker


class TestCoalesceTracker:
    def test_first_detection_returns_none(self):
        tracker = CoalesceTracker(window_s=30)
        result = tracker.check("cam-1", "person")
        assert result is None

    def test_detection_within_window_returns_event_id(self):
        tracker = CoalesceTracker(window_s=30)
        tracker.record("cam-1", "person", "evt-1", end_time=time.time())
        result = tracker.check("cam-1", "person")
        assert result == "evt-1"

    def test_detection_outside_window_returns_none(self):
        tracker = CoalesceTracker(window_s=30)
        old = time.time() - 60
        tracker.record("cam-1", "person", "evt-1", end_time=old)
        result = tracker.check("cam-1", "person")
        assert result is None

    def test_different_camera_not_coalesced(self):
        tracker = CoalesceTracker(window_s=30)
        tracker.record("cam-1", "person", "evt-1", end_time=time.time())
        result = tracker.check("cam-2", "person")
        assert result is None

    def test_different_type_not_coalesced(self):
        tracker = CoalesceTracker(window_s=30)
        tracker.record("cam-1", "person", "evt-1", end_time=time.time())
        result = tracker.check("cam-1", "vehicle")
        assert result is None

    def test_record_updates_existing_entry(self):
        tracker = CoalesceTracker(window_s=30)
        tracker.record("cam-1", "person", "evt-1", end_time=time.time() - 20)
        tracker.record("cam-1", "person", "evt-2", end_time=time.time())
        result = tracker.check("cam-1", "person")
        assert result == "evt-2"

    def test_expire_removes_old_entries(self):
        tracker = CoalesceTracker(window_s=30)
        old = time.time() - 60
        tracker.record("cam-1", "person", "evt-1", end_time=old)
        tracker.record("cam-2", "vehicle", "evt-2", end_time=time.time())
        tracker.expire()
        assert tracker.check("cam-1", "person") is None
        assert tracker.check("cam-2", "vehicle") == "evt-2"

    def test_zero_window_never_coalesces(self):
        tracker = CoalesceTracker(window_s=0)
        tracker.record("cam-1", "person", "evt-1", end_time=time.time())
        result = tracker.check("cam-1", "person")
        assert result is None

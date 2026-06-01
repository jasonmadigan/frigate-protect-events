"""unit tests for EventProcessor: snapshot timing and event lifecycle.

the daytime-snapshot bug: fetching at new grabs frigate's previous (often
daytime) frame because this event's best frame is not written until end.
these tests pin the correct behaviour: authoritative fetch at end, and a
freshness gate at new so a stale frame is never stored."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from frigate_protect_events.camera_cache import CameraInfo
from frigate_protect_events.models import FrigateEvent
from frigate_protect_events.processor import EventProcessor


def _after(**overrides):
    base = {
        "id": "frigate-evt-1",
        "camera": "front_door",
        "label": "person",
        "score": 0.9,
        "top_score": 0.95,
        "start_time": 1700000000.0,
        "end_time": None,
        "has_snapshot": False,
    }
    base.update(overrides)
    return base


def _build(fetch, resolve=CameraInfo("cam-uuid-1", None), check=None):
    cameras = MagicMock()
    cameras.resolve.return_value = resolve
    writer = MagicMock()
    tracker = MagicMock()
    tracker.check.return_value = check
    cfg = SimpleNamespace(frigate_host="192.168.1.5")
    proc = EventProcessor(cameras, writer, tracker, cfg, fetch=fetch)
    return proc, writer, tracker


class TestNewEventSnapshot:
    def test_does_not_fetch_when_snapshot_not_ready(self):
        fetch = MagicMock()
        proc, writer, _ = _build(fetch)

        proc.handle("new", FrigateEvent.from_mqtt(_after()))

        fetch.assert_not_called()
        writer.write_detection.assert_called_once()
        assert writer.write_detection.call_args[0][1] is None

    def test_does_not_fetch_stale_frame(self):
        # snapshot frame predates this event -> previous (daytime) frame
        fetch = MagicMock()
        proc, writer, _ = _build(fetch)
        evt = FrigateEvent.from_mqtt(
            _after(has_snapshot=True, snapshot={"frame_time": 1699990000.0})
        )

        proc.handle("new", evt)

        fetch.assert_not_called()
        assert writer.write_detection.call_args[0][1] is None

    def test_fetches_fresh_frame(self):
        fetch = MagicMock(return_value=b"\xff\xd8fresh")
        proc, writer, _ = _build(fetch)
        evt = FrigateEvent.from_mqtt(
            _after(has_snapshot=True, snapshot={"frame_time": 1700000000.5})
        )

        proc.handle("new", evt)

        fetch.assert_called_once_with("192.168.1.5", "frigate-evt-1")
        assert writer.write_detection.call_args[0][1] == b"\xff\xd8fresh"


class TestCoalescing:
    def test_new_coalesces_into_existing_event(self):
        fetch = MagicMock()
        proc, writer, _ = _build(fetch, check="existing-event-id")

        proc.handle("new", FrigateEvent.from_mqtt(_after()))

        writer.write_detection.assert_not_called()
        writer.write_coalesced_detection.assert_called_once()
        assert writer.write_coalesced_detection.call_args[0][1] == "existing-event-id"


class TestEndEvent:
    def test_fetches_finalised_snapshot_and_overwrites_thumbnail(self):
        fetch = MagicMock(return_value=b"\xff\xd8final")
        proc, writer, tracker = _build(fetch)

        # new first to register the frigate->protect id mapping
        proc.handle("new", FrigateEvent.from_mqtt(_after()))
        event_id = writer.write_detection.call_args[0][0].event_id
        fetch.reset_mock()

        end = FrigateEvent.from_mqtt(
            _after(end_time=1700000010.0, has_snapshot=True)
        )
        proc.handle("end", end)

        fetch.assert_called_once_with("192.168.1.5", "frigate-evt-1")
        writer.update_event_end.assert_called_once_with(event_id, 1700000010000)
        writer.set_event_thumbnail.assert_called_once_with(event_id, b"\xff\xd8final")
        tracker.record.assert_called_once()

    def test_unknown_frigate_id_writes_nothing(self):
        fetch = MagicMock()
        proc, writer, _ = _build(fetch)

        proc.handle("end", FrigateEvent.from_mqtt(_after(end_time=1700000010.0)))

        writer.update_event_end.assert_not_called()
        writer.set_event_thumbnail.assert_not_called()


class TestGuards:
    def test_unknown_camera_skipped(self):
        fetch = MagicMock()
        proc, writer, _ = _build(fetch, resolve=None)

        proc.handle("new", FrigateEvent.from_mqtt(_after()))

        writer.write_detection.assert_not_called()

    def test_unmapped_label_skipped(self):
        fetch = MagicMock()
        proc, writer, _ = _build(fetch)

        proc.handle("new", FrigateEvent.from_mqtt(_after(label="robot_lawnmower")))

        writer.write_detection.assert_not_called()

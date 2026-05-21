"""unit tests for protect_writer using a mock db.
integration tests against real postgres are in test_integration.py."""

import json
from unittest.mock import MagicMock, call

from frigate_protect_events.models import FrigateEvent, ProtectDetection
from frigate_protect_events.protect_writer import ProtectWriter


SAMPLE_AFTER = {
    "id": "frigate-evt-1",
    "camera": "front_door",
    "label": "person",
    "score": 0.95,
    "top_score": 0.98,
    "start_time": 1700000000.0,
    "end_time": None,
    "has_snapshot": True,
}


def _make_detection(**overrides) -> ProtectDetection:
    evt = FrigateEvent.from_mqtt({**SAMPLE_AFTER, **overrides})
    return ProtectDetection.from_frigate_event(evt, "cam-uuid-1")


class TestCreateEvent:
    def test_inserts_event_row(self):
        db = MagicMock()
        writer = ProtectWriter(db)
        det = _make_detection()

        writer.create_event(det)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "INSERT INTO events" in sql
        assert "smartDetectZone" in sql
        params = db.execute.call_args[0][1]
        assert params[0] == det.event_id
        assert params[1] == det.start_ms
        assert params[2] == det.camera_id


class TestEndEvent:
    def test_updates_event_end(self):
        db = MagicMock()
        writer = ProtectWriter(db)

        writer.update_event_end("evt-id", 1700000010000)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert 'UPDATE events SET "end"' in sql
        params = db.execute.call_args[0][1]
        assert params[0] == 1700000010000
        assert params[2] == "evt-id"


class TestCreateSdo:
    def test_inserts_sdo_row(self):
        db = MagicMock()
        writer = ProtectWriter(db)
        det = _make_detection()

        writer.create_sdo(det)

        sql = db.execute.call_args[0][0]
        assert 'INSERT INTO "smartDetectObjects"' in sql
        params = db.execute.call_args[0][1]
        assert params[0] == det.sdo_id
        assert params[1] == det.event_id
        assert params[4] == det.detect_type


class TestCreateRaw:
    def test_inserts_raw_row(self):
        db = MagicMock()
        writer = ProtectWriter(db)
        det = _make_detection()

        writer.create_raw(det)

        sql = db.execute.call_args[0][0]
        assert 'INSERT INTO "smartDetectRaws"' in sql


class TestCreateTrack:
    def test_inserts_track_row(self):
        db = MagicMock()
        writer = ProtectWriter(db)
        det = _make_detection()

        writer.create_track(det)

        sql = db.execute.call_args[0][0]
        assert 'INSERT INTO "smartDetectTracks"' in sql


class TestUpsertLabels:
    def test_upserts_three_labels(self):
        db = MagicMock()
        # return sequential lids
        db.fetchone = MagicMock(side_effect=[
            {"lid": 1}, {"lid": 2}, {"lid": 3},
        ])
        writer = ProtectWriter(db)
        det = _make_detection()

        lids = writer.upsert_labels(det)

        assert lids == [1, 2, 3]
        assert db.fetchone.call_count == 3


class TestCreateDetectionLabels:
    def test_inserts_two_rows(self):
        db = MagicMock()
        writer = ProtectWriter(db)
        det = _make_detection()

        writer.create_detection_labels(det, [1, 2, 3])

        assert db.execute.call_count == 2
        # first call: event-level (objectId = '')
        first_params = db.execute.call_args_list[0][0][1]
        assert first_params[2] == ""
        # second call: sdo-level (objectId = sdo_id)
        second_params = db.execute.call_args_list[1][0][1]
        assert second_params[2] == det.sdo_id


class TestCreateThumbnail:
    def test_inserts_thumbnail_with_jpeg(self):
        db = MagicMock()
        writer = ProtectWriter(db)
        det = _make_detection()
        jpeg = b"\xff\xd8\xff\xe0JFIF"

        writer.create_thumbnail(det, jpeg)

        sql = db.execute.call_args[0][0]
        assert "INSERT INTO thumbnails" in sql
        params = db.execute.call_args[0][1]
        assert params[0] == det.thumbnail_id
        assert params[6] == jpeg

    def test_skips_when_no_jpeg(self):
        db = MagicMock()
        writer = ProtectWriter(db)
        det = _make_detection()

        writer.create_thumbnail(det, None)

        db.execute.assert_not_called()


class TestWriteDetection:
    def test_orchestrates_all_operations(self):
        db = MagicMock()
        db.fetchone = MagicMock(side_effect=[
            {"lid": 1}, {"lid": 2}, {"lid": 3},
        ])
        writer = ProtectWriter(db)
        det = _make_detection()
        jpeg = b"\xff\xd8"

        writer.write_detection(det, jpeg)

        # should have called execute multiple times + commit
        assert db.execute.call_count >= 7
        db.commit.assert_called_once()

    def test_rolls_back_on_error(self):
        db = MagicMock()
        db.execute.side_effect = Exception("db error")
        writer = ProtectWriter(db)
        det = _make_detection()

        try:
            writer.write_detection(det, None)
        except Exception:
            pass

        db.rollback.assert_called_once()

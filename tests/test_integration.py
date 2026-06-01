"""integration tests against real postgres.
requires: docker compose -f docker-compose.test.yaml up -d"""

import json

import pytest

from tests.conftest import requires_db, TEST_DB_HOST, TEST_DB_PORT, TEST_DB_NAME, TEST_DB_USER
from frigate_protect_events.db import ProtectDb
from frigate_protect_events.models import FrigateEvent, ProtectDetection
from frigate_protect_events.protect_writer import ProtectWriter
from frigate_protect_events.camera_cache import CameraCache


CAMERA_UUID = "test-camera-uuid-1234"

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


def _make_db() -> ProtectDb:
    db = ProtectDb()
    db.connect(TEST_DB_HOST, TEST_DB_PORT, TEST_DB_NAME, TEST_DB_USER)
    return db


@requires_db
class TestIntegrationNewEvent:
    def test_write_detection_creates_all_rows(self, db_conn):
        db = _make_db()
        try:
            writer = ProtectWriter(db)
            evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
            det = ProtectDetection.from_frigate_event(evt, CAMERA_UUID)
            jpeg = b"\xff\xd8\xff\xe0test-jpeg"

            writer.write_detection(det, jpeg)

            # verify events table
            row = db.fetchone('SELECT * FROM events WHERE id = %s', (det.event_id,))
            assert row is not None
            assert row["type"] == "smartDetectZone"
            assert row["start"] == 1700000000000
            assert row["end"] is None
            assert row["cameraId"] == CAMERA_UUID
            meta = row["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            assert meta["source"] == "frigate-protect-events"

            # verify smartDetectObjects
            sdo = db.fetchone(
                'SELECT * FROM "smartDetectObjects" WHERE id = %s', (det.sdo_id,)
            )
            assert sdo is not None
            assert sdo["eventId"] == det.event_id
            assert sdo["type"] == "person"

            # verify smartDetectRaws
            raw = db.fetchone(
                'SELECT * FROM "smartDetectRaws" WHERE id = %s', (det.raw_id,)
            )
            assert raw is not None

            # verify smartDetectTracks
            track = db.fetchone(
                'SELECT * FROM "smartDetectTracks" WHERE id = %s', (det.track_id,)
            )
            assert track is not None
            assert track["eventId"] == det.event_id

            # verify labels (3 labels created)
            labels = db.fetchall('SELECT * FROM labels')
            assert len(labels) == 3
            label_names = {l["name"] for l in labels}
            assert "eventType:smartDetectZone" in label_names
            assert "smartDetectType:person" in label_names
            assert f"camera:{CAMERA_UUID}" in label_names

            # verify labels have lastSeen
            for label in labels:
                assert label["lastSeen"] == 1700000000000

            # verify detectionLabels (2 rows)
            dl = db.fetchall(
                'SELECT * FROM "detectionLabels" WHERE "eventId" = %s',
                (det.event_id,),
            )
            assert len(dl) == 2
            # one with objectId NULL, one with sdo_id
            object_ids = {d["objectId"] for d in dl}
            assert None in object_ids
            assert det.sdo_id in object_ids

            # verify thumbnail
            thumb = db.fetchone('SELECT * FROM thumbnails WHERE id = %s', (det.thumbnail_id,))
            assert thumb is not None
            assert bytes(thumb["content"]) == jpeg
        finally:
            db.close()

    def test_write_detection_skips_thumbnail_when_no_jpeg(self, db_conn):
        db = _make_db()
        try:
            writer = ProtectWriter(db)
            evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
            det = ProtectDetection.from_frigate_event(evt, CAMERA_UUID)

            writer.write_detection(det, None)

            thumb = db.fetchone('SELECT * FROM thumbnails WHERE id = %s', (det.thumbnail_id,))
            assert thumb is None
        finally:
            db.close()


@requires_db
class TestIntegrationThumbnailOverwrite:
    def test_set_event_thumbnail_inserts_then_overwrites(self, db_conn):
        db = _make_db()
        try:
            writer = ProtectWriter(db)
            evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
            det = ProtectDetection.from_frigate_event(evt, CAMERA_UUID)
            writer.write_detection(det, None)  # no thumbnail at new

            assert db.fetchone(
                "SELECT * FROM thumbnails WHERE id = %s", (det.thumbnail_id,)
            ) is None

            # finalised frame fetched at end
            writer.set_event_thumbnail(det.event_id, b"\xff\xd8night")
            thumb = db.fetchone(
                "SELECT * FROM thumbnails WHERE id = %s", (det.thumbnail_id,)
            )
            assert thumb is not None
            assert bytes(thumb["content"]) == b"\xff\xd8night"

            # a later end overwrites in place, no duplicate row
            writer.set_event_thumbnail(det.event_id, b"\xff\xd8better")
            rows = db.fetchall(
                "SELECT * FROM thumbnails WHERE id = %s", (det.thumbnail_id,)
            )
            assert len(rows) == 1
            assert bytes(rows[0]["content"]) == b"\xff\xd8better"
        finally:
            db.close()

    def test_set_event_thumbnail_noop_without_jpeg(self, db_conn):
        db = _make_db()
        try:
            writer = ProtectWriter(db)
            evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
            det = ProtectDetection.from_frigate_event(evt, CAMERA_UUID)
            writer.write_detection(det, None)

            writer.set_event_thumbnail(det.event_id, None)

            assert db.fetchone(
                "SELECT * FROM thumbnails WHERE id = %s", (det.thumbnail_id,)
            ) is None
        finally:
            db.close()


@requires_db
class TestIntegrationEndEvent:
    def test_update_event_end_sets_timestamp(self, db_conn):
        db = _make_db()
        try:
            writer = ProtectWriter(db)
            evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
            det = ProtectDetection.from_frigate_event(evt, CAMERA_UUID)

            writer.write_detection(det, None)

            # now end the event
            writer.update_event_end(det.event_id, 1700000010000)

            row = db.fetchone('SELECT * FROM events WHERE id = %s', (det.event_id,))
            assert row["end"] == 1700000010000
        finally:
            db.close()


@requires_db
class TestIntegrationCoalescing:
    def test_coalesced_detection_reuses_event(self, db_conn):
        db = _make_db()
        try:
            writer = ProtectWriter(db)

            # first detection
            evt1 = FrigateEvent.from_mqtt(SAMPLE_AFTER)
            det1 = ProtectDetection.from_frigate_event(evt1, CAMERA_UUID)
            writer.write_detection(det1, None)

            # coalesced detection (same event id)
            after2 = {**SAMPLE_AFTER, "id": "frigate-evt-2", "start_time": 1700000005.0}
            evt2 = FrigateEvent.from_mqtt(after2)
            det2 = ProtectDetection.from_frigate_event(evt2, CAMERA_UUID)
            writer.write_coalesced_detection(det2, det1.event_id, None)

            # should have 1 event, 2 SDOs
            events = db.fetchall('SELECT * FROM events')
            assert len(events) == 1

            sdos = db.fetchall('SELECT * FROM "smartDetectObjects"')
            assert len(sdos) == 2
            assert all(s["eventId"] == det1.event_id for s in sdos)
        finally:
            db.close()

    def test_coalesced_detection_labels_upsert_no_conflict(self, db_conn):
        """detectionLabels UPSERT should handle coalesced events without unique violation."""
        db = _make_db()
        try:
            writer = ProtectWriter(db)

            evt1 = FrigateEvent.from_mqtt(SAMPLE_AFTER)
            det1 = ProtectDetection.from_frigate_event(evt1, CAMERA_UUID)
            writer.write_detection(det1, None)

            # coalesced detection reuses the same event id
            after2 = {**SAMPLE_AFTER, "id": "frigate-evt-2", "start_time": 1700000005.0}
            evt2 = FrigateEvent.from_mqtt(after2)
            det2 = ProtectDetection.from_frigate_event(evt2, CAMERA_UUID)

            # this should NOT raise a unique constraint violation
            writer.write_coalesced_detection(det2, det1.event_id, None)

            # verify detection labels exist
            dl = db.fetchall(
                'SELECT * FROM "detectionLabels" WHERE "eventId" = %s',
                (det1.event_id,),
            )
            # event-level row (1) + sdo-level rows (2, one per SDO)
            assert len(dl) >= 2
        finally:
            db.close()


@requires_db
class TestIntegrationCameraCache:
    def test_auto_discover_cameras(self, db_conn):
        # insert test cameras
        db_conn.execute(
            'INSERT INTO cameras (id, mac, host, name, "isThirdPartyCamera", "isAdopted") '
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("uuid-1", "AA:BB:CC:DD:EE:FF", "192.168.1.100", "front_door", True, True),
        )
        db_conn.execute(
            'INSERT INTO cameras (id, mac, host, name, "isThirdPartyCamera", "isAdopted") '
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("uuid-2", "11:22:33:44:55:66", "192.168.1.101", "back_garden", True, True),
        )
        # non-adopted camera should be excluded
        db_conn.execute(
            'INSERT INTO cameras (id, mac, host, name, "isThirdPartyCamera", "isAdopted") '
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("uuid-3", "77:88:99:AA:BB:CC", "192.168.1.102", "garage", True, False),
        )

        db = _make_db()
        try:
            cache = CameraCache(db=db, config_map={})
            cache.load_from_db()

            front = cache.resolve("front_door")
            assert front is not None
            assert front.uuid == "uuid-1"
            assert front.mac == "AA:BB:CC:DD:EE:FF"

            back = cache.resolve("back_garden")
            assert back is not None
            assert back.uuid == "uuid-2"
            assert back.mac == "11:22:33:44:55:66"

            assert cache.resolve("garage") is None
        finally:
            db.close()

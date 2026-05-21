import json
import re
import uuid

from frigate_protect_events.models import FrigateEvent, ProtectDetection


SAMPLE_AFTER = {
    "id": "abc-frigate-123",
    "camera": "front_door",
    "label": "person",
    "score": 0.95,
    "top_score": 0.98,
    "box": [100, 200, 300, 400],
    "area": 5000,
    "region": [50, 50, 500, 500],
    "frame_time": 1700000000.5,
    "start_time": 1700000000.0,
    "end_time": None,
    "has_snapshot": True,
    "has_clip": False,
    "current_zones": ["front_yard"],
    "entered_zones": ["front_yard"],
    "stationary": False,
}


class TestFrigateEvent:
    def test_from_mqtt_payload(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        assert evt.id == "abc-frigate-123"
        assert evt.camera == "front_door"
        assert evt.label == "person"
        assert evt.score == 0.95
        assert evt.top_score == 0.98
        assert evt.start_time == 1700000000.0
        assert evt.end_time is None
        assert evt.has_snapshot is True

    def test_from_mqtt_with_end_time(self):
        data = {**SAMPLE_AFTER, "end_time": 1700000010.0}
        evt = FrigateEvent.from_mqtt(data)
        assert evt.end_time == 1700000010.0

    def test_from_mqtt_minimal_fields(self):
        minimal = {
            "id": "x",
            "camera": "cam1",
            "label": "car",
            "score": 0.5,
            "start_time": 1000.0,
        }
        evt = FrigateEvent.from_mqtt(minimal)
        assert evt.id == "x"
        assert evt.camera == "cam1"
        assert evt.label == "car"
        assert evt.top_score == 0.5
        assert evt.end_time is None
        assert evt.has_snapshot is False


class TestProtectDetection:
    def test_from_frigate_event_generates_ids(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(
            evt, "cam-uuid-1", camera_mac="AA:BB:CC:DD:EE:FF"
        )

        # event id is valid uuid4
        uuid.UUID(det.event_id, version=4)
        uuid.UUID(det.sdo_id, version=4)
        uuid.UUID(det.raw_id, version=4)
        uuid.UUID(det.track_id, version=4)

    def test_thumbnail_id_uses_mac_and_timestamp(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(
            evt, "cam-uuid-1", camera_mac="AA:BB:CC:DD:EE:FF"
        )
        # format: {MAC_no_colons}-{start_ms}
        assert det.thumbnail_id == "AABBCCDDEEFF-1700000000000"

    def test_thumbnail_id_without_mac_falls_back_to_hex(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        # no mac provided, should fall back to random hex
        assert re.match(r"^[0-9a-f]{24}$", det.thumbnail_id)

    def test_timestamps_are_epoch_ms(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")

        assert det.start_ms == 1700000000000
        assert det.end_ms is None

    def test_end_time_converted_to_ms(self):
        data = {**SAMPLE_AFTER, "end_time": 1700000010.5}
        evt = FrigateEvent.from_mqtt(data)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        assert det.end_ms == 1700000010500

    def test_smart_detect_types_json(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        parsed = json.loads(det.smart_detect_types_json)
        assert parsed == ["person"]

    def test_camera_uuid_stored(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        assert det.camera_id == "cam-uuid-1"

    def test_detect_type(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        assert det.detect_type == "person"

    def test_vehicle_detect_type(self):
        data = {**SAMPLE_AFTER, "label": "car"}
        evt = FrigateEvent.from_mqtt(data)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        assert det.detect_type == "vehicle"
        parsed = json.loads(det.smart_detect_types_json)
        assert parsed == ["vehicle"]

    def test_created_at_is_iso_utc(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        assert det.created_at.endswith("Z") or "+00:00" in det.created_at

    def test_raw_payload_structure(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        payload = json.loads(det.raw_payload_json)
        assert "descriptors" in payload
        assert payload["descriptors"][0]["objectType"] == "person"
        assert "clockWall" in payload
        assert "zonesStatus" in payload

    def test_track_payload_structure(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        payload = json.loads(det.track_payload_json)
        assert isinstance(payload, list)
        assert payload[0]["objectType"] == "person"
        assert "timestamp" in payload[0]
        assert "duration" in payload[0]

    def test_sdo_attributes(self):
        evt = FrigateEvent.from_mqtt(SAMPLE_AFTER)
        det = ProtectDetection.from_frigate_event(evt, "cam-uuid-1")
        attrs = json.loads(det.sdo_attributes_json)
        assert attrs["objectType"] == "person"
        assert "trackerId" in attrs

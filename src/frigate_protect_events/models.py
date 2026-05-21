from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from frigate_protect_events.labels import map_label, smart_detect_types


@dataclass(frozen=True)
class FrigateEvent:
    id: str
    camera: str
    label: str
    score: float
    top_score: float
    start_time: float
    end_time: float | None
    has_snapshot: bool

    @classmethod
    def from_mqtt(cls, after: dict) -> FrigateEvent:
        return cls(
            id=after["id"],
            camera=after["camera"],
            label=after["label"],
            score=after["score"],
            top_score=after.get("top_score", after["score"]),
            start_time=after["start_time"],
            end_time=after.get("end_time"),
            has_snapshot=after.get("has_snapshot", False),
        )


def _uuid4() -> str:
    return str(uuid.uuid4())


def _thumbnail_id() -> str:
    """24-char random hex. protect checks id length to decide storage:
    len==24 -> thumbnails DB table, len!=24 -> ubv video file extraction."""
    return os.urandom(12).hex()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ProtectDetection:
    event_id: str
    sdo_id: str
    raw_id: str
    track_id: str
    thumbnail_id: str
    camera_id: str
    detect_type: str
    start_ms: int
    end_ms: int | None
    smart_detect_types_json: str
    sdo_attributes_json: str
    raw_payload_json: str
    track_payload_json: str
    created_at: str
    frigate_event_id: str

    @classmethod
    def from_frigate_event(
        cls,
        event: FrigateEvent,
        camera_uuid: str,
    ) -> ProtectDetection:
        detect_type = map_label(event.label) or event.label
        start_ms = int(event.start_time * 1000)
        end_ms = int(event.end_time * 1000) if event.end_time else None
        now = _iso_now()

        sdo_attributes = {
            "objectType": detect_type,
            "trackerId": 1,
            "confidence": 0,
        }

        raw_payload = {
            "descriptors": [
                {
                    "coord": [-1, -1, -1, -1],
                    "objectType": detect_type,
                    "confidence": 75,
                }
            ],
            "clockStream": 0,
            "clockWall": start_ms,
            "zonesStatus": {},
        }

        track_payload = [
            {
                "coord": [-1, -1, -1, -1],
                "objectType": detect_type,
                "confidence": 75,
                "duration": 0,
                "timestamp": start_ms,
            }
        ]

        return cls(
            event_id=_uuid4(),
            sdo_id=_uuid4(),
            raw_id=_uuid4(),
            track_id=_uuid4(),
            thumbnail_id=_thumbnail_id(),
            camera_id=camera_uuid,
            detect_type=detect_type,
            start_ms=start_ms,
            end_ms=end_ms,
            smart_detect_types_json=json.dumps(smart_detect_types(event.label)),
            sdo_attributes_json=json.dumps(sdo_attributes),
            raw_payload_json=json.dumps(raw_payload),
            track_payload_json=json.dumps(track_payload),
            created_at=now,
            frigate_event_id=event.id,
        )

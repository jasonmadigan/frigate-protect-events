from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from frigate_protect_events.db import ProtectDb

from frigate_protect_events.models import ProtectDetection

log = logging.getLogger(__name__)

_INSERT_EVENT = """\
INSERT INTO events
  (id, type, start, "cameraId", score, "smartDetectTypes",
   metadata, locked, "thumbnailId", "createdAt", "updatedAt")
VALUES (%s, 'smartDetectZone', %s::bigint, %s, 100, %s::json,
        '{"source":"frigate-protect-events"}'::json, false, %s, %s, %s)
"""

_UPDATE_EVENT_END = """\
UPDATE events SET "end" = %s::bigint, "updatedAt" = %s WHERE id = %s
"""

_INSERT_SDO = """\
INSERT INTO "smartDetectObjects"
  (id, "eventId", "thumbnailId", "cameraId", type, attributes,
   "detectedAt", metadata, "createdAt", "updatedAt")
VALUES (%s, %s, %s, %s, %s, %s::json, %s::bigint,
        '{}'::jsonb, %s, %s)
"""

_INSERT_RAW = """\
INSERT INTO "smartDetectRaws"
  (id, "cameraId", payload, timestamp, "createdAt", "updatedAt")
VALUES (%s, %s, %s::json, %s::bigint, %s, %s)
"""

_INSERT_TRACK = """\
INSERT INTO "smartDetectTracks"
  (id, "eventId", "cameraId", payload, "createdAt", "updatedAt")
VALUES (%s, %s, %s, %s::json, %s, %s)
"""

_UPSERT_LABEL = """\
INSERT INTO labels (id, name, "lastSeen", "createdAt", "updatedAt")
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (name) DO UPDATE SET "lastSeen" = EXCLUDED."lastSeen", "updatedAt" = EXCLUDED."updatedAt"
RETURNING lid
"""

_UPSERT_EVENT_DETECTION_LABEL = """\
INSERT INTO "detectionLabels"
  (id, "eventId", "objectId", labels, "createdAt", "updatedAt")
VALUES (%s, %s, NULL, %s::integer[], %s, %s)
ON CONFLICT ("eventId") WHERE "objectId" IS NULL
DO UPDATE SET labels = EXCLUDED.labels, "updatedAt" = EXCLUDED."updatedAt"
"""

_UPSERT_SDO_DETECTION_LABEL = """\
INSERT INTO "detectionLabels"
  (id, "eventId", "objectId", labels, "createdAt", "updatedAt")
VALUES (%s, %s, %s, %s::integer[], %s, %s)
ON CONFLICT ("eventId", "objectId") WHERE "objectId" IS NOT NULL
DO UPDATE SET labels = EXCLUDED.labels, "updatedAt" = EXCLUDED."updatedAt"
"""

_INSERT_THUMBNAIL = """\
INSERT INTO thumbnails
  (id, "cameraId", "eventId", timestamp, "createdAt",
   "updatedAt", content, "isFullfov")
VALUES (%s, %s, %s, %s::bigint, %s, %s, %s, false)
ON CONFLICT (id) DO NOTHING
"""


def _uuid4() -> str:
    return str(uuid.uuid4())


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProtectWriter:
    def __init__(self, db: ProtectDb) -> None:
        self._db = db

    def create_event(self, det: ProtectDetection) -> None:
        self._db.execute(
            _INSERT_EVENT,
            (
                det.event_id,
                det.start_ms,
                det.camera_id,
                det.smart_detect_types_json,
                det.thumbnail_id,
                det.created_at,
                det.created_at,
            ),
        )

    def update_event_end(self, event_id: str, end_ms: int) -> None:
        now = _iso_now()
        self._db.execute(_UPDATE_EVENT_END, (end_ms, now, event_id))
        self._db.commit()

    def create_sdo(self, det: ProtectDetection) -> None:
        self._db.execute(
            _INSERT_SDO,
            (
                det.sdo_id,
                det.event_id,
                det.thumbnail_id,
                det.camera_id,
                det.detect_type,
                det.sdo_attributes_json,
                det.start_ms,
                det.created_at,
                det.created_at,
            ),
        )

    def create_raw(self, det: ProtectDetection) -> None:
        self._db.execute(
            _INSERT_RAW,
            (
                det.raw_id,
                det.camera_id,
                det.raw_payload_json,
                det.start_ms,
                det.created_at,
                det.created_at,
            ),
        )

    def create_track(self, det: ProtectDetection) -> None:
        self._db.execute(
            _INSERT_TRACK,
            (
                det.track_id,
                det.event_id,
                det.camera_id,
                det.track_payload_json,
                det.created_at,
                det.created_at,
            ),
        )

    def upsert_labels(self, det: ProtectDetection) -> list[int]:
        now = _iso_now()
        label_names = [
            "eventType:smartDetectZone",
            f"smartDetectType:{det.detect_type}",
            f"camera:{det.camera_id}",
        ]
        lids = []
        for name in label_names:
            row = self._db.fetchone(
                _UPSERT_LABEL, (_uuid4(), name, det.start_ms, now, now)
            )
            lids.append(row["lid"])
        return lids

    def create_detection_labels(
        self, det: ProtectDetection, lids: list[int]
    ) -> None:
        now = _iso_now()
        # event-level: objectId = NULL (hardcoded in SQL)
        self._db.execute(
            _UPSERT_EVENT_DETECTION_LABEL,
            (_uuid4(), det.event_id, lids, now, now),
        )
        # sdo-level
        self._db.execute(
            _UPSERT_SDO_DETECTION_LABEL,
            (_uuid4(), det.event_id, det.sdo_id, lids, now, now),
        )

    def create_thumbnail(
        self, det: ProtectDetection, jpeg: bytes | None
    ) -> None:
        if jpeg is None:
            return
        self._db.execute(
            _INSERT_THUMBNAIL,
            (
                det.thumbnail_id,
                det.camera_id,
                det.event_id,
                det.start_ms,
                det.created_at,
                det.created_at,
                jpeg,
            ),
        )

    def write_detection(
        self, det: ProtectDetection, jpeg: bytes | None
    ) -> None:
        try:
            self.create_event(det)
            self.create_sdo(det)
            self.create_raw(det)
            self.create_track(det)
            lids = self.upsert_labels(det)
            self.create_detection_labels(det, lids)
            self.create_thumbnail(det, jpeg)
            self._db.commit()
            log.info(
                "wrote detection: event=%s type=%s camera=%s",
                det.event_id,
                det.detect_type,
                det.camera_id,
            )
        except Exception:
            self._db.rollback()
            raise

    def write_coalesced_detection(
        self, det: ProtectDetection, existing_event_id: str, jpeg: bytes | None
    ) -> None:
        """write sdo/raw/track/labels for a coalesced detection, reusing an existing event."""
        # patch the detection to reference the existing event
        det = ProtectDetection(
            event_id=existing_event_id,
            sdo_id=det.sdo_id,
            raw_id=det.raw_id,
            track_id=det.track_id,
            thumbnail_id=det.thumbnail_id,
            camera_id=det.camera_id,
            detect_type=det.detect_type,
            start_ms=det.start_ms,
            end_ms=det.end_ms,
            smart_detect_types_json=det.smart_detect_types_json,
            sdo_attributes_json=det.sdo_attributes_json,
            raw_payload_json=det.raw_payload_json,
            track_payload_json=det.track_payload_json,
            created_at=det.created_at,
            frigate_event_id=det.frigate_event_id,
        )
        try:
            self.create_sdo(det)
            self.create_raw(det)
            self.create_track(det)
            lids = self.upsert_labels(det)
            self.create_detection_labels(det, lids)
            self.create_thumbnail(det, jpeg)
            self._db.commit()
            log.info(
                "wrote coalesced detection: event=%s type=%s",
                existing_event_id,
                det.detect_type,
            )
        except Exception:
            self._db.rollback()
            raise

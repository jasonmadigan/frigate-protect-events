from __future__ import annotations

import logging
from typing import Callable

from frigate_protect_events.camera_cache import CameraCache
from frigate_protect_events.coalesce import CoalesceTracker
from frigate_protect_events.config import Config
from frigate_protect_events.labels import map_label
from frigate_protect_events.models import FrigateEvent, ProtectDetection
from frigate_protect_events.protect_writer import ProtectWriter
from frigate_protect_events.snapshot import fetch_snapshot

log = logging.getLogger(__name__)

# (frigate_host, event_id) -> jpeg bytes or None
SnapshotFetcher = Callable[["str | None", str], "bytes | None"]


class EventProcessor:
    """turns frigate new/end events into protect detections.

    frigate writes an event's best frame to disk only when tracking ends, so
    the authoritative snapshot is fetched at end. at new the event's own frame
    is usually not ready and the api can hand back the previous event's frame
    (a daytime frame at night), so new only stores a snapshot it can prove
    belongs to this event."""

    def __init__(
        self,
        cameras: CameraCache,
        writer: ProtectWriter,
        tracker: CoalesceTracker,
        cfg: Config,
        fetch: SnapshotFetcher = fetch_snapshot,
    ) -> None:
        self._cameras = cameras
        self._writer = writer
        self._tracker = tracker
        self._cfg = cfg
        self._fetch = fetch
        # frigate event id -> protect event id, for end events
        self._event_map: dict[str, str] = {}

    def handle(self, event_type: str, event: FrigateEvent) -> None:
        cam = self._cameras.resolve(event.camera)
        if not cam:
            log.warning("unknown camera: %s, skipping", event.camera)
            return

        detect_type = map_label(event.label)
        if not detect_type:
            return

        if event_type == "new":
            self._on_new(event, cam.uuid, detect_type)
        elif event_type == "end":
            self._on_end(event, cam.uuid, detect_type)

        self._tracker.expire()

    def _on_new(
        self, event: FrigateEvent, camera_uuid: str, detect_type: str
    ) -> None:
        det = ProtectDetection.from_frigate_event(event, camera_uuid)
        jpeg = self._snapshot_if_fresh(event)

        existing = self._tracker.check(camera_uuid, detect_type)
        if existing:
            self._writer.write_coalesced_detection(det, existing, jpeg)
            self._event_map[event.id] = existing
            log.info("coalesced %s into existing event %s", event.id, existing)
        else:
            self._writer.write_detection(det, jpeg)
            self._event_map[event.id] = det.event_id

    def _on_end(
        self, event: FrigateEvent, camera_uuid: str, detect_type: str
    ) -> None:
        protect_event_id = self._event_map.pop(event.id, None)
        if not protect_event_id:
            log.warning("end event for unknown frigate id: %s", event.id)
            return

        if event.end_time:
            end_ms = int(event.end_time * 1000)
            self._writer.update_event_end(protect_event_id, end_ms)
            self._tracker.record(
                camera_uuid, detect_type, protect_event_id, event.end_time
            )

        # tracking has ended, so frigate's best frame is now finalised. fetch
        # it and overwrite whatever (if anything) we stored at new.
        self._writer.set_event_thumbnail(protect_event_id, self._snapshot(event))

    def _snapshot(self, event: FrigateEvent) -> bytes | None:
        if event.has_snapshot and self._cfg.frigate_host:
            return self._fetch(self._cfg.frigate_host, event.id)
        return None

    def _snapshot_if_fresh(self, event: FrigateEvent) -> bytes | None:
        ft = event.snapshot_frame_time
        if ft is None or ft < event.start_time:
            return None
        return self._snapshot(event)

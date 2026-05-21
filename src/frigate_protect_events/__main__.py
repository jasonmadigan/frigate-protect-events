from __future__ import annotations

import logging
import os
import signal
import sys
import time

from frigate_protect_events.camera_cache import CameraCache
from frigate_protect_events.coalesce import CoalesceTracker
from frigate_protect_events.config import load_config
from frigate_protect_events.db import ProtectDb
from frigate_protect_events.labels import map_label
from frigate_protect_events.models import FrigateEvent, ProtectDetection
from frigate_protect_events.mqtt import MqttSubscriber
from frigate_protect_events.protect_writer import ProtectWriter
from frigate_protect_events.snapshot import fetch_snapshot
from frigate_protect_events.tunnel import SshTunnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("frigate_protect_events")


def main() -> None:
    config_path = (
        sys.argv[1]
        if len(sys.argv) >= 2
        else os.environ.get("FPE_CONFIG")
    )
    if not config_path:
        print(
            "usage: python -m frigate_protect_events <config.yaml>\n"
            "  or set FPE_CONFIG=/path/to/config.yaml",
            file=sys.stderr,
        )
        sys.exit(1)
    cfg = load_config(config_path)
    log.info("loaded config from %s", config_path)

    # ssh tunnel
    tunnel = SshTunnel(cfg.protect)
    local_port = tunnel.connect()

    # database
    db = ProtectDb()
    db.connect("127.0.0.1", local_port, cfg.protect.db_name, cfg.protect.db_user)

    # camera cache
    cameras = CameraCache(db=db, config_map=cfg.cameras)
    cameras.load_from_db()

    # writer and coalescing
    writer = ProtectWriter(db)
    tracker = CoalesceTracker(cfg.coalesce_window_s)

    # tracks frigate event id -> protect event id for end events
    event_map: dict[str, str] = {}

    def on_event(event_type: str, event: FrigateEvent) -> None:
        cam_info = cameras.resolve(event.camera)
        if not cam_info:
            log.warning("unknown camera: %s, skipping", event.camera)
            return

        camera_uuid = cam_info.uuid
        detect_type = map_label(event.label)
        if not detect_type:
            return

        if event_type == "new":
            det = ProtectDetection.from_frigate_event(event, camera_uuid)

            # check coalescing
            existing = tracker.check(camera_uuid, detect_type)
            if existing:
                writer.write_coalesced_detection(det, existing, _get_snapshot(cfg, event))
                event_map[event.id] = existing
                log.info("coalesced %s into existing event %s", event.id, existing)
            else:
                jpeg = _get_snapshot(cfg, event)
                writer.write_detection(det, jpeg)
                event_map[event.id] = det.event_id

        elif event_type == "end":
            protect_event_id = event_map.pop(event.id, None)
            if not protect_event_id:
                log.warning("end event for unknown frigate id: %s", event.id)
                return

            end_ms = int(event.end_time * 1000) if event.end_time else None
            if end_ms:
                writer.update_event_end(protect_event_id, end_ms)
                tracker.record(camera_uuid, detect_type, protect_event_id, event.end_time)

        # periodic cleanup
        tracker.expire()

    def _get_snapshot(cfg, event: FrigateEvent) -> bytes | None:
        if event.has_snapshot and cfg.frigate_host:
            return fetch_snapshot(cfg.frigate_host, event.id)
        return None

    # graceful shutdown
    mqtt_sub = MqttSubscriber(cfg.mqtt, on_event)

    def shutdown(signum, frame):
        log.info("shutting down (signal %d)", signum)
        mqtt_sub.stop()
        db.close()
        tunnel.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    log.info("starting mqtt subscriber")
    mqtt_sub.start()


if __name__ == "__main__":
    main()

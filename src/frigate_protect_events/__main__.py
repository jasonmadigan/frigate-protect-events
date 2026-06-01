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
from frigate_protect_events.mqtt import MqttSubscriber
from frigate_protect_events.processor import EventProcessor
from frigate_protect_events.protect_writer import ProtectWriter
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

    # writer, coalescing and event processing
    writer = ProtectWriter(db)
    tracker = CoalesceTracker(cfg.coalesce_window_s)
    processor = EventProcessor(cameras, writer, tracker, cfg)

    # graceful shutdown
    mqtt_sub = MqttSubscriber(cfg.mqtt, processor.handle)

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

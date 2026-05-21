from __future__ import annotations

import logging
from typing import NamedTuple, TYPE_CHECKING

if TYPE_CHECKING:
    from frigate_protect_events.db import ProtectDb

log = logging.getLogger(__name__)

_CAMERA_QUERY = """\
SELECT id, mac, host, name
FROM cameras
WHERE "isThirdPartyCamera" = true
  AND "isAdopted" = true
  AND host IS NOT NULL
"""


class CameraInfo(NamedTuple):
    uuid: str
    mac: str | None


class CameraCache:
    def __init__(
        self,
        db: ProtectDb,
        config_map: dict[str, str],
    ) -> None:
        self._db = db
        self._config_map = {k.lower(): v for k, v in config_map.items()}
        self._db_map: dict[str, CameraInfo] = {}

    def load_from_db(self) -> None:
        rows = self._db.fetchall(_CAMERA_QUERY)
        self._db_map = {
            row["name"].lower(): CameraInfo(uuid=row["id"], mac=row["mac"])
            for row in rows
        }
        log.info("discovered %d cameras from protect db", len(self._db_map))
        for name, info in self._db_map.items():
            log.info("  %s -> %s", name, info.uuid)

    def resolve(self, frigate_name: str) -> CameraInfo | None:
        # config overrides take precedence (no mac available from config)
        key = frigate_name.lower()
        if key in self._config_map:
            return CameraInfo(uuid=self._config_map[key], mac=None)
        return self._db_map.get(key)


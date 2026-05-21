from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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


class CameraCache:
    def __init__(
        self,
        db: ProtectDb,
        config_map: dict[str, str],
    ) -> None:
        self._db = db
        self._config_map = dict(config_map)
        self._db_map: dict[str, str] = {}

    def load_from_db(self) -> None:
        rows = self._db.fetchall(_CAMERA_QUERY)
        self._db_map = {row["name"]: row["id"] for row in rows}
        log.info("discovered %d cameras from protect db", len(self._db_map))
        for name, uid in self._db_map.items():
            log.info("  %s -> %s", name, uid)

    def resolve(self, frigate_name: str) -> str | None:
        # config overrides take precedence
        if frigate_name in self._config_map:
            return self._config_map[frigate_name]
        return self._db_map.get(frigate_name)

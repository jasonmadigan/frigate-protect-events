from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Entry:
    event_id: str
    end_time: float


class CoalesceTracker:
    """tracks recent detections to avoid creating duplicate events
    when a detection ends and restarts within a short window."""

    def __init__(self, window_s: int) -> None:
        self._window_s = window_s
        self._entries: dict[tuple[str, str], _Entry] = {}

    def check(self, camera_id: str, detect_type: str) -> str | None:
        if self._window_s <= 0:
            return None
        key = (camera_id, detect_type)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.time() - entry.end_time <= self._window_s:
            return entry.event_id
        return None

    def record(
        self, camera_id: str, detect_type: str, event_id: str, end_time: float
    ) -> None:
        key = (camera_id, detect_type)
        self._entries[key] = _Entry(event_id=event_id, end_time=end_time)

    def expire(self) -> None:
        now = time.time()
        stale = [
            k
            for k, v in self._entries.items()
            if now - v.end_time > self._window_s
        ]
        for k in stale:
            del self._entries[k]

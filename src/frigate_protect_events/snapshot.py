from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


def fetch_snapshot(frigate_host: str | None, event_id: str) -> bytes | None:
    if not frigate_host:
        return None

    url = f"http://{frigate_host}:5000/api/events/{event_id}/snapshot.jpg"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.content
        log.warning("snapshot fetch returned %d for %s", resp.status_code, event_id)
        return None
    except requests.RequestException as exc:
        log.warning("snapshot fetch failed for %s: %s", event_id, exc)
        return None

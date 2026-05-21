from __future__ import annotations

_LABEL_MAP: dict[str, str] = {
    "person": "person",
    "car": "vehicle",
    "motorcycle": "vehicle",
    "bus": "vehicle",
    "truck": "vehicle",
    "dog": "animal",
    "cat": "animal",
    "bird": "animal",
    "package": "package",
}


def map_label(frigate_label: str) -> str | None:
    return _LABEL_MAP.get(frigate_label)


def smart_detect_types(frigate_label: str) -> list[str]:
    t = map_label(frigate_label)
    return [t] if t else []

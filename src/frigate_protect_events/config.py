from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int = 1883
    topic_prefix: str = "frigate"
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class ProtectConfig:
    host: str
    ssh_key: str
    ssh_user: str = "root"
    ssh_port: int = 22
    db_port: int = 5433
    db_name: str = "unifi-protect"
    db_user: str = "postgres"


@dataclass(frozen=True)
class Config:
    mqtt: MqttConfig
    protect: ProtectConfig
    cameras: dict[str, str] = field(default_factory=dict)
    coalesce_window_s: int = 30
    frigate_host: str | None = None


def load_config(path: str | Path) -> Config:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")

    with open(p) as f:
        raw = yaml.safe_load(f) or {}

    mqtt_raw = raw.get("mqtt") or {}
    protect_raw = raw.get("protect") or {}

    if not mqtt_raw.get("host"):
        raise ValueError("mqtt.host is required")
    if not protect_raw.get("host"):
        raise ValueError("protect.host is required")
    if not protect_raw.get("ssh_key"):
        raise ValueError("protect.ssh_key is required")

    mqtt = MqttConfig(
        host=mqtt_raw["host"],
        port=mqtt_raw.get("port", 1883),
        topic_prefix=mqtt_raw.get("topic_prefix", "frigate"),
        username=mqtt_raw.get("username"),
        password=mqtt_raw.get("password"),
    )

    protect = ProtectConfig(
        host=protect_raw["host"],
        ssh_key=protect_raw["ssh_key"],
        ssh_user=protect_raw.get("ssh_user", "root"),
        ssh_port=protect_raw.get("ssh_port", 22),
        db_port=protect_raw.get("db_port", 5433),
        db_name=protect_raw.get("db_name", "unifi-protect"),
        db_user=protect_raw.get("db_user", "postgres"),
    )

    return Config(
        mqtt=mqtt,
        protect=protect,
        cameras=raw.get("cameras") or {},
        coalesce_window_s=raw.get("coalesce_window_s", 30),
        frigate_host=raw.get("frigate_host"),
    )

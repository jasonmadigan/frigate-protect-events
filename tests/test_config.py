import pytest
import tempfile
import os
from pathlib import Path

from frigate_protect_events.config import Config, load_config


MINIMAL_YAML = """\
mqtt:
  host: 192.168.1.10
protect:
  host: 192.168.1.20
  ssh_key: /tmp/fake_key
"""

FULL_YAML = """\
mqtt:
  host: 192.168.1.10
  port: 1884
  topic_prefix: cam
  username: user1
  password: pass1
protect:
  host: 192.168.1.20
  ssh_user: admin
  ssh_key: /tmp/fake_key
  ssh_port: 2222
  db_port: 5555
  db_name: my-protect
  db_user: myuser
cameras:
  front_door: "abc-123"
  back_garden: "def-456"
coalesce_window_s: 60
frigate_host: 192.168.1.30
"""


def _write_yaml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return f.name


class TestLoadConfig:
    def test_minimal_config_sets_defaults(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            cfg = load_config(path)
            assert cfg.mqtt.host == "192.168.1.10"
            assert cfg.mqtt.port == 1883
            assert cfg.mqtt.topic_prefix == "frigate"
            assert cfg.mqtt.username is None
            assert cfg.mqtt.password is None
            assert cfg.protect.host == "192.168.1.20"
            assert cfg.protect.ssh_user == "root"
            assert cfg.protect.ssh_port == 22
            assert cfg.protect.db_port == 5433
            assert cfg.protect.db_name == "unifi-protect"
            assert cfg.protect.db_user == "postgres"
            assert cfg.cameras == {}
            assert cfg.coalesce_window_s == 30
            assert cfg.frigate_host is None
            assert cfg.write_thumbnail_to_db is False
        finally:
            os.unlink(path)

    def test_write_thumbnail_to_db_opt_in(self):
        yaml = MINIMAL_YAML + "write_thumbnail_to_db: true\n"
        path = _write_yaml(yaml)
        try:
            cfg = load_config(path)
            assert cfg.write_thumbnail_to_db is True
        finally:
            os.unlink(path)

    def test_full_config_overrides_all(self):
        path = _write_yaml(FULL_YAML)
        try:
            cfg = load_config(path)
            assert cfg.mqtt.host == "192.168.1.10"
            assert cfg.mqtt.port == 1884
            assert cfg.mqtt.topic_prefix == "cam"
            assert cfg.mqtt.username == "user1"
            assert cfg.mqtt.password == "pass1"
            assert cfg.protect.host == "192.168.1.20"
            assert cfg.protect.ssh_user == "admin"
            assert cfg.protect.ssh_port == 2222
            assert cfg.protect.db_port == 5555
            assert cfg.protect.db_name == "my-protect"
            assert cfg.protect.db_user == "myuser"
            assert cfg.cameras == {
                "front_door": "abc-123",
                "back_garden": "def-456",
            }
            assert cfg.coalesce_window_s == 60
            assert cfg.frigate_host == "192.168.1.30"
        finally:
            os.unlink(path)

    def test_missing_mqtt_host_raises(self):
        path = _write_yaml("protect:\n  host: 1.2.3.4\n  ssh_key: /tmp/k\n")
        try:
            with pytest.raises(ValueError, match="mqtt.host"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_protect_host_raises(self):
        path = _write_yaml("mqtt:\n  host: 1.2.3.4\n")
        try:
            with pytest.raises(ValueError, match="protect.host"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_protect_ssh_key_raises(self):
        path = _write_yaml("mqtt:\n  host: 1.2.3.4\nprotect:\n  host: 1.2.3.4\n")
        try:
            with pytest.raises(ValueError, match="protect.ssh_key"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")

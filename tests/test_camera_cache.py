from unittest.mock import MagicMock

from frigate_protect_events.camera_cache import CameraCache


class TestCameraCache:
    def test_config_override_takes_precedence(self):
        db = MagicMock()
        cache = CameraCache(
            db=db,
            config_map={"front_door": "override-uuid"},
        )
        assert cache.resolve("front_door") == "override-uuid"
        db.execute.assert_not_called()

    def test_auto_discover_from_db(self):
        db = MagicMock()
        db.fetchall.return_value = [
            {"id": "uuid-1", "name": "front_door", "mac": "aa:bb", "host": "1.2.3.4"},
            {"id": "uuid-2", "name": "back_garden", "mac": "cc:dd", "host": "1.2.3.5"},
        ]
        cache = CameraCache(db=db, config_map={})
        cache.load_from_db()

        assert cache.resolve("front_door") == "uuid-1"
        assert cache.resolve("back_garden") == "uuid-2"

    def test_unknown_camera_returns_none(self):
        db = MagicMock()
        db.fetchall.return_value = []
        cache = CameraCache(db=db, config_map={})
        cache.load_from_db()
        assert cache.resolve("nonexistent") is None

    def test_config_overrides_db(self):
        db = MagicMock()
        db.fetchall.return_value = [
            {"id": "db-uuid", "name": "front_door", "mac": "aa:bb", "host": "1.2.3.4"},
        ]
        cache = CameraCache(
            db=db,
            config_map={"front_door": "config-uuid"},
        )
        cache.load_from_db()
        assert cache.resolve("front_door") == "config-uuid"

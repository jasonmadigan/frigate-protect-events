from unittest.mock import MagicMock

from frigate_protect_events.camera_cache import CameraCache, CameraInfo


class TestCameraCache:
    def test_config_override_takes_precedence(self):
        db = MagicMock()
        cache = CameraCache(
            db=db,
            config_map={"front_door": "override-uuid"},
        )
        result = cache.resolve("front_door")
        assert result is not None
        assert result.uuid == "override-uuid"
        # config overrides don't have a mac
        assert result.mac is None
        db.execute.assert_not_called()

    def test_auto_discover_from_db(self):
        db = MagicMock()
        db.fetchall.return_value = [
            {"id": "uuid-1", "name": "front_door", "mac": "AA:BB:CC:DD:EE:FF", "host": "1.2.3.4"},
            {"id": "uuid-2", "name": "back_garden", "mac": "11:22:33:44:55:66", "host": "1.2.3.5"},
        ]
        cache = CameraCache(db=db, config_map={})
        cache.load_from_db()

        front = cache.resolve("front_door")
        assert front is not None
        assert front.uuid == "uuid-1"
        assert front.mac == "AA:BB:CC:DD:EE:FF"

        back = cache.resolve("back_garden")
        assert back is not None
        assert back.uuid == "uuid-2"
        assert back.mac == "11:22:33:44:55:66"

    def test_unknown_camera_returns_none(self):
        db = MagicMock()
        db.fetchall.return_value = []
        cache = CameraCache(db=db, config_map={})
        cache.load_from_db()
        assert cache.resolve("nonexistent") is None

    def test_case_insensitive_db_lookup(self):
        db = MagicMock()
        db.fetchall.return_value = [
            {"id": "uuid-pump", "name": "Pumphouse", "mac": "AA:BB:CC:DD:EE:01", "host": "1.2.3.6"},
        ]
        cache = CameraCache(db=db, config_map={})
        cache.load_from_db()

        result = cache.resolve("pumphouse")
        assert result is not None
        assert result.uuid == "uuid-pump"
        assert result.mac == "AA:BB:CC:DD:EE:01"

    def test_case_insensitive_config_lookup(self):
        db = MagicMock()
        cache = CameraCache(
            db=db,
            config_map={"Front_Door": "cfg-uuid"},
        )
        result = cache.resolve("front_door")
        assert result is not None
        assert result.uuid == "cfg-uuid"

    def test_config_overrides_db(self):
        db = MagicMock()
        db.fetchall.return_value = [
            {"id": "db-uuid", "name": "front_door", "mac": "AA:BB:CC:DD:EE:FF", "host": "1.2.3.4"},
        ]
        cache = CameraCache(
            db=db,
            config_map={"front_door": "config-uuid"},
        )
        cache.load_from_db()
        result = cache.resolve("front_door")
        assert result is not None
        assert result.uuid == "config-uuid"

    def test_explicit_config_skips_db_discovery(self):
        db = MagicMock()
        cache = CameraCache(
            db=db,
            config_map={"garage_rear": "uuid-garage", "pumphouse": "uuid-pump"},
        )
        cache.load_from_db()
        # db should never be queried
        db.fetchall.assert_not_called()
        # only config cameras resolve
        assert cache.resolve("garage_rear").uuid == "uuid-garage"
        assert cache.resolve("pumphouse").uuid == "uuid-pump"
        assert cache.resolve("gate") is None

    def test_empty_config_triggers_db_discovery(self):
        db = MagicMock()
        db.fetchall.return_value = [
            {"id": "uuid-gate", "name": "gate", "mac": "AA:BB:CC:DD:EE:02", "host": "1.2.3.7"},
        ]
        cache = CameraCache(db=db, config_map={})
        cache.load_from_db()
        db.fetchall.assert_called_once()
        assert cache.resolve("gate").uuid == "uuid-gate"

    def test_has_config_mappings_property(self):
        db = MagicMock()
        empty = CameraCache(db=db, config_map={})
        assert not empty.has_config_mappings
        populated = CameraCache(db=db, config_map={"cam": "uuid"})
        assert populated.has_config_mappings

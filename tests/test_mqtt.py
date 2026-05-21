import json
from unittest.mock import MagicMock

from frigate_protect_events.mqtt import MqttSubscriber
from frigate_protect_events.models import FrigateEvent


SAMPLE_NEW = {
    "type": "new",
    "before": {},
    "after": {
        "id": "evt-1",
        "camera": "front_door",
        "label": "person",
        "score": 0.9,
        "top_score": 0.95,
        "start_time": 1700000000.0,
        "end_time": None,
        "has_snapshot": True,
    },
}

SAMPLE_END = {
    "type": "end",
    "before": {},
    "after": {
        "id": "evt-1",
        "camera": "front_door",
        "label": "person",
        "score": 0.9,
        "top_score": 0.95,
        "start_time": 1700000000.0,
        "end_time": 1700000010.0,
        "has_snapshot": True,
    },
}

SAMPLE_UPDATE = {
    "type": "update",
    "before": {},
    "after": {
        "id": "evt-1",
        "camera": "front_door",
        "label": "person",
        "score": 0.9,
        "start_time": 1700000000.0,
    },
}


class TestMqttSubscriber:
    def _make_msg(self, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.payload = json.dumps(payload).encode()
        return msg

    def test_new_event_calls_handler(self):
        handler = MagicMock()
        sub = MqttSubscriber.__new__(MqttSubscriber)
        sub._handler = handler
        sub._on_message(None, None, self._make_msg(SAMPLE_NEW))
        handler.assert_called_once()
        call_args = handler.call_args
        assert call_args[0][0] == "new"
        assert isinstance(call_args[0][1], FrigateEvent)
        assert call_args[0][1].id == "evt-1"

    def test_end_event_calls_handler(self):
        handler = MagicMock()
        sub = MqttSubscriber.__new__(MqttSubscriber)
        sub._handler = handler
        sub._on_message(None, None, self._make_msg(SAMPLE_END))
        handler.assert_called_once()
        assert handler.call_args[0][0] == "end"

    def test_update_event_ignored(self):
        handler = MagicMock()
        sub = MqttSubscriber.__new__(MqttSubscriber)
        sub._handler = handler
        sub._on_message(None, None, self._make_msg(SAMPLE_UPDATE))
        handler.assert_not_called()

    def test_unmapped_label_ignored(self):
        payload = {
            "type": "new",
            "before": {},
            "after": {
                "id": "evt-2",
                "camera": "cam",
                "label": "robot_lawnmower",
                "score": 0.8,
                "start_time": 1000.0,
            },
        }
        handler = MagicMock()
        sub = MqttSubscriber.__new__(MqttSubscriber)
        sub._handler = handler
        sub._on_message(None, None, self._make_msg(payload))
        handler.assert_not_called()

    def test_malformed_json_does_not_crash(self):
        handler = MagicMock()
        sub = MqttSubscriber.__new__(MqttSubscriber)
        sub._handler = handler
        msg = MagicMock()
        msg.payload = b"not json at all"
        sub._on_message(None, None, msg)
        handler.assert_not_called()

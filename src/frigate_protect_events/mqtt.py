from __future__ import annotations

import json
import logging
from typing import Callable

import paho.mqtt.client as mqtt

from frigate_protect_events.config import MqttConfig
from frigate_protect_events.labels import map_label
from frigate_protect_events.models import FrigateEvent

log = logging.getLogger(__name__)

# handler signature: (event_type: str, event: FrigateEvent) -> None
EventHandler = Callable[[str, FrigateEvent], None]


class MqttSubscriber:
    def __init__(
        self, config: MqttConfig, handler: EventHandler
    ) -> None:
        self._config = config
        self._handler = handler
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if config.username:
            self._client.username_pw_set(config.username, config.password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        topic = f"{self._config.topic_prefix}/events"
        client.subscribe(topic)
        log.info("subscribed to %s", topic)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("malformed mqtt message, skipping")
            return

        event_type = payload.get("type")
        if event_type not in ("new", "end"):
            return

        after = payload.get("after", {})
        label = after.get("label", "")
        if not map_label(label):
            return

        try:
            event = FrigateEvent.from_mqtt(after)
            self._handler(event_type, event)
        except Exception:
            log.exception("error processing event %s", after.get("id"))

    def start(self) -> None:
        self._client.connect(self._config.host, self._config.port)
        self._client.loop_forever()

    def stop(self) -> None:
        self._client.disconnect()

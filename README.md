# frigate-protect-events

Bridges Frigate NVR AI detections into UniFi Protect as native smart detection events.

Frigate does the AI detection (person, car, animal, etc.) via YOLO. This service subscribes to Frigate's MQTT events, SSHes into the UniFi Protect console, and writes detections directly into Protect's PostgreSQL database. Events appear on the Protect timeline, in smart detection search, and can trigger native alarms.

## How it works

```
Frigate (YOLO) --> MQTT (frigate/events) --> this service --> SSH --> Protect PostgreSQL
```

1. Subscribes to Frigate's `{topic_prefix}/events` MQTT topic
2. On `new` or `end` event types, maps the Frigate camera name to a Protect camera UUID
3. SSHes into the Protect console and executes SQL against the local PostgreSQL instance (`dbname=unifi user=protect`)
4. Creates/updates rows in Protect's internal tables so the detection appears as a native smart detection event

## Protect DB tables

| Table | Purpose |
|-|-|
| `events` | The detection event (type, score, camera, timestamps) |
| `smartDetectObjects` | Links detection type (person/vehicle) to event |
| `smartDetectRaws` | Required for timeline display |
| `smartDetectTracks` | Required for iOS app search |
| `labels` + `detectionLabels` | Required for filtering/search |
| `thumbnails` | JPEG thumbnail for the UI |
| `cameras` | Read-only, maps camera names to Protect UUIDs |

## Frigate MQTT event payload

Events arrive on `{prefix}/events` as JSON with `type` (new/update/end), `before`, and `after` objects containing:

- `camera`: camera name string
- `label`: detection type (person, car, dog, etc.)
- `score` / `top_score`: confidence values
- `box`: bounding box coordinates `[x1, y1, x2, y2]`
- `start_time` / `end_time`: epoch timestamps
- `has_snapshot`: whether a snapshot is available
- Snapshot image available as base64 in the payload or via `{prefix}/{camera}/{label}/snapshot` MQTT topic

## Label mapping

| Frigate label | Protect smartDetectType |
|-|-|
| person | person |
| car / motorcycle / bus / truck | vehicle |
| dog / cat / bird | animal |
| package | package |

## Configuration

```yaml
mqtt:
  host: 192.168.1.x
  port: 1883
  topic_prefix: frigate

protect:
  host: 192.168.1.x  # UDM/UNVR IP
  ssh_user: root
  ssh_key: ~/.ssh/id_rsa

cameras:
  # frigate camera name -> protect camera UUID
  # if omitted, auto-discovered from protect's cameras table
  front_door: "abc123-def456-..."
  back_garden: "789xyz-..."
```

## Risks

This writes directly to Protect's internal PostgreSQL schema. Ubiquiti can change this schema on any firmware update without notice. The core `events` table structure has been stable for a while, but there are no guarantees. Test after every Protect firmware update.

## Prior art

- [danielwoz/ubiquiti-protect-onvif-event-listener](https://github.com/danielwoz/ubiquiti-protect-onvif-event-listener) -- C++ binary that does ONVIF-to-Protect event injection with its own detection engine. This project borrows the DB schema knowledge but takes a simpler approach: Frigate already does the detection, we just write the results.

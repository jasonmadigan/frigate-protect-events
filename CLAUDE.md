# frigate-protect-events

Bridges Frigate NVR AI detections into UniFi Protect as native smart detection events.

## Architecture

```
Frigate (YOLO) --> MQTT (frigate/events) --> this service --> SSH tunnel --> Protect PostgreSQL
```

Python service. Subscribes to Frigate MQTT events, opens an SSH tunnel to the Protect console,
writes detections directly into Protect's internal PostgreSQL database.

## Stack

- Python 3.11+
- `paho-mqtt` for MQTT subscription
- `paramiko` for SSH tunnel to Protect console
- `psycopg` (v3) for PostgreSQL over the SSH tunnel
- Docker for deployment

## Protect PostgreSQL connection

Connection is local-only on the console. We SSH tunnel to reach it.

```
host=/run/postgresql port=5433 dbname=unifi-protect user=postgres
```

Via SSH tunnel, connect to `localhost:{tunnel_port}` with `dbname=unifi-protect user=postgres`.

## Frigate MQTT event payload

Topic: `{topic_prefix}/events` (default prefix: `frigate`)

```json
{
  "type": "new|update|end",
  "before": { ... },
  "after": {
    "id": "uuid-string",
    "camera": "camera_name",
    "label": "person",
    "score": 0.95,
    "top_score": 0.98,
    "box": [x1, y1, x2, y2],
    "area": 5000,
    "region": [rx1, ry1, rx2, ry2],
    "frame_time": 1234567890.5,
    "start_time": 1234567890.0,
    "end_time": null,
    "has_snapshot": true,
    "has_clip": false,
    "current_zones": ["front_yard"],
    "entered_zones": ["front_yard"],
    "stationary": false,
    "sub_label": ["adult", 0.88],
    "attributes": [{"label": "standing", "score": 0.9, "box": [...]}]
  }
}
```

Snapshots also published as binary JPEG to `{prefix}/{camera}/{label}/snapshot`.

Frigate HTTP API for snapshots: `GET http://{frigate_host}:5000/api/events/{event_id}/snapshot.jpg`

### Event lifecycle

- `type: "new"` -- first detection, `end_time` is null
- `type: "update"` -- ongoing tracking, fires frequently (every few hundred ms)
- `type: "end"` -- object left frame or tracking lost, `end_time` is set

We only care about `new` (create DB records) and `end` (update event end timestamp).
Ignore `update` events to avoid hammering the DB.

## Label mapping

| Frigate label | Protect `smartDetectTypes` |
|-|-|
| person | `["person"]` |
| car, motorcycle, bus, truck, bicycle, boat | `["vehicle"]` |
| dog, cat, bird, fox, deer, rabbit, horse, cow | `["animal"]` |
| package | `["package"]` |

## Protect DB schema and SQL

All IDs are UUID v4. All timestamps are epoch milliseconds (bigint).
`createdAt`/`updatedAt` are ISO-8601 UTC strings.

### 1. Look up camera UUID

```sql
SELECT id, mac, host, name
FROM cameras
WHERE "isThirdPartyCamera" = true
  AND "isAdopted" = true
  AND host IS NOT NULL
```

Map Frigate camera names to Protect camera UUIDs. Cache at startup.

### 2. INSERT event (on detection start)

```sql
INSERT INTO events
  (id, type, start, "cameraId", score, "smartDetectTypes",
   metadata, locked, "thumbnailId", "createdAt", "updatedAt")
VALUES ($1, 'smartDetectZone', $2::bigint, $3, 100, $4::json,
        '{"source":"frigate-protect-events"}'::json, false, $5, $6, $7)
```

- `$1`: new UUID v4
- `$2`: `start_time * 1000` (epoch ms)
- `$3`: Protect camera UUID
- `$4`: e.g. `["person"]`
- `$5`: thumbnail ID (24-char random hex)
- `$6, $7`: ISO-8601 UTC now

### 3. UPDATE event (on detection end)

```sql
UPDATE events SET "end" = $1::bigint, "updatedAt" = $2 WHERE id = $3
```

- `$1`: `end_time * 1000` (epoch ms)

### 4. INSERT smartDetectObjects

```sql
INSERT INTO "smartDetectObjects"
  (id, "eventId", "thumbnailId", "cameraId", type, attributes,
   "detectedAt", metadata, "createdAt", "updatedAt")
VALUES ($1, $2, $3, $4, $5, $6::json, $7::bigint,
        '{}'::jsonb, $8, $9)
```

- `type`: `"person"`, `"vehicle"`, `"animal"`, `"package"`
- `attributes`: `{"objectType": "person", "trackerId": 1, "confidence": 0}`

### 5. INSERT smartDetectRaws

```sql
INSERT INTO "smartDetectRaws"
  (id, "cameraId", payload, timestamp, "createdAt", "updatedAt")
VALUES ($1, $2, $3::json, $4::bigint, $5, $6)
```

`payload` format:
```json
{
  "descriptors": [{
    "coord": [-1, -1, -1, -1],
    "objectType": "person",
    "confidence": 75
  }],
  "clockStream": 0,
  "clockWall": 1234567890000,
  "zonesStatus": {}
}
```

### 6. INSERT smartDetectTracks

```sql
INSERT INTO "smartDetectTracks"
  (id, "eventId", "cameraId", payload, "createdAt", "updatedAt")
VALUES ($1, $2, $3, $4::json, $5, $6)
```

`payload`: `[{"coord": [-1,-1,-1,-1], "objectType": "person", "confidence": 75, "duration": 0, "timestamp": 1234567890000}]`

Required for iOS "Find Anything" feature.

### 7. UPSERT labels

```sql
INSERT INTO labels (id, name, "lastSeen", "createdAt", "updatedAt")
VALUES ($1, $2, $3, $4, $4)
ON CONFLICT (name) DO UPDATE SET "lastSeen" = EXCLUDED."lastSeen", "updatedAt" = EXCLUDED."updatedAt"
RETURNING lid
```

- `$3`: detection timestamp (epoch ms)

Create labels for: `eventType:smartDetectZone`, `smartDetectType:person`, `camera:{uuid}`.
`lid` is auto-increment integer used in `detectionLabels`.

### 8. UPSERT detectionLabels

Event-level row (objectId IS NULL):
```sql
INSERT INTO "detectionLabels"
  (id, "eventId", "objectId", labels, "createdAt", "updatedAt")
VALUES ($1, $2, NULL, $3::integer[], $4, $5)
ON CONFLICT ("eventId") WHERE "objectId" IS NULL
DO UPDATE SET labels = EXCLUDED.labels, "updatedAt" = EXCLUDED."updatedAt"
```

SDO-level row (objectId IS NOT NULL):
```sql
INSERT INTO "detectionLabels"
  (id, "eventId", "objectId", labels, "createdAt", "updatedAt")
VALUES ($1, $2, $3, $4::integer[], $5, $6)
ON CONFLICT ("eventId", "objectId") WHERE "objectId" IS NOT NULL
DO UPDATE SET labels = EXCLUDED.labels, "updatedAt" = EXCLUDED."updatedAt"
```

Two rows per detection. The event-level row is required for Protect's search INNER JOIN.
UPSERT handles coalesced events without unique constraint violations.

### 9. Thumbnail storage

Protect uses `thumbnailId.length` to decide where to fetch thumbnail data:
- `length === 24`: reads from `thumbnails` DB table (`content` column, bytea)
- `length !== 24`: extracts from `.ubv` video files on the filesystem

We don't have UBV video for Frigate cameras, so thumbnailId must always be exactly
24 chars (random hex via `os.urandom(12).hex()`). We always write to the DB table
when snapshot data is available.

```sql
INSERT INTO thumbnails
  (id, "cameraId", "eventId", timestamp, "createdAt",
   "updatedAt", content, "isFullfov")
VALUES ($1, $2, $3, $4::bigint, $5, $6, $7, false)
ON CONFLICT (id) DO NOTHING
```

### Event coalescing

If a new detection starts within 30s of the previous end for the same camera+type,
reuse the existing event row. Insert new SDO/raw/track/label rows referencing the same
event ID. Don't create a new event row.

### Cleanup

Use `metadata::jsonb->>'source' = 'frigate-protect-events'` to identify our events
for cleanup/debugging. Never touch events from other sources.

## Configuration

```yaml
mqtt:
  host: 192.168.1.x
  port: 1883
  topic_prefix: frigate
  # username/password if needed

protect:
  host: 192.168.1.x
  ssh_user: root
  ssh_key: ~/.ssh/id_rsa
  ssh_port: 22
  db_port: 5433
  db_name: unifi-protect
  db_user: postgres

cameras:
  # frigate_name: protect_uuid
  # if empty, auto-discovered from cameras table
  front_door: "abc123-..."

coalesce_window_s: 30
```

## Risks

- Protect DB schema can change on any firmware update
- No official API for event creation
- SSH access to console required
- Test after every Protect firmware update
- Prior art: danielwoz/ubiquiti-protect-onvif-event-listener (C++ binary, much more complex)

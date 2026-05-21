-- minimal protect schema for integration tests

CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    mac TEXT,
    host TEXT,
    name TEXT,
    "isThirdPartyCamera" BOOLEAN DEFAULT false,
    "isAdopted" BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    start BIGINT,
    "end" BIGINT,
    "cameraId" TEXT,
    score INTEGER,
    "smartDetectTypes" JSON,
    metadata JSON,
    locked BOOLEAN DEFAULT false,
    "thumbnailId" TEXT,
    "createdAt" TEXT,
    "updatedAt" TEXT
);

CREATE TABLE IF NOT EXISTS "smartDetectObjects" (
    id TEXT PRIMARY KEY,
    "eventId" TEXT,
    "thumbnailId" TEXT,
    "cameraId" TEXT,
    type TEXT,
    attributes JSON,
    "detectedAt" BIGINT,
    metadata JSONB,
    "createdAt" TEXT,
    "updatedAt" TEXT
);

CREATE TABLE IF NOT EXISTS "smartDetectRaws" (
    id TEXT PRIMARY KEY,
    "cameraId" TEXT,
    payload JSON,
    timestamp BIGINT,
    "createdAt" TEXT,
    "updatedAt" TEXT
);

CREATE TABLE IF NOT EXISTS "smartDetectTracks" (
    id TEXT PRIMARY KEY,
    "eventId" TEXT,
    "cameraId" TEXT,
    payload JSON,
    "createdAt" TEXT,
    "updatedAt" TEXT
);

CREATE TABLE IF NOT EXISTS labels (
    lid SERIAL,
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    "lastSeen" BIGINT,
    "createdAt" TEXT,
    "updatedAt" TEXT
);

CREATE TABLE IF NOT EXISTS "detectionLabels" (
    id TEXT PRIMARY KEY,
    "eventId" TEXT,
    "objectId" TEXT,
    labels INTEGER[],
    "createdAt" TEXT,
    "updatedAt" TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS "detectionLabels_eventId_null_objectId"
    ON "detectionLabels" ("eventId") WHERE "objectId" IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "detectionLabels_eventId_objectId"
    ON "detectionLabels" ("eventId", "objectId") WHERE "objectId" IS NOT NULL;


CREATE TABLE IF NOT EXISTS thumbnails (
    id TEXT PRIMARY KEY,
    "cameraId" TEXT,
    "eventId" TEXT,
    timestamp BIGINT,
    "createdAt" TEXT,
    "updatedAt" TEXT,
    content BYTEA,
    "isFullfov" BOOLEAN DEFAULT false
);

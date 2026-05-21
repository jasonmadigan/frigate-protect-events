import os
import pytest
import psycopg

TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "127.0.0.1")
TEST_DB_PORT = int(os.environ.get("TEST_DB_PORT", "15433"))
TEST_DB_NAME = "unifi-protect"
TEST_DB_USER = "postgres"


def _db_available() -> bool:
    try:
        conn = psycopg.connect(
            host=TEST_DB_HOST,
            port=TEST_DB_PORT,
            dbname=TEST_DB_NAME,
            user=TEST_DB_USER,
            autocommit=True,
        )
        conn.close()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="test postgres not available (run: docker compose -f docker-compose.test.yaml up -d)",
)


@pytest.fixture
def db_conn():
    conn = psycopg.connect(
        host=TEST_DB_HOST,
        port=TEST_DB_PORT,
        dbname=TEST_DB_NAME,
        user=TEST_DB_USER,
        autocommit=True,
    )
    # clean all tables before each test
    for table in [
        "thumbnails",
        '"detectionLabels"',
        "labels",
        '"smartDetectTracks"',
        '"smartDetectRaws"',
        '"smartDetectObjects"',
        "events",
        "cameras",
    ]:
        conn.execute(f"DELETE FROM {table}")
    yield conn
    conn.close()

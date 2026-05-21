from __future__ import annotations

import logging
from typing import Any

import psycopg

log = logging.getLogger(__name__)


class ProtectDb:
    def __init__(self) -> None:
        self._conn: psycopg.Connection | None = None

    def connect(self, host: str, port: int, dbname: str, user: str) -> None:
        self._conn = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            autocommit=False,
        )
        log.info("connected to %s@%s:%d/%s", user, host, port, dbname)

    @property
    def conn(self) -> psycopg.Connection:
        if self._conn is None:
            raise RuntimeError("not connected")
        return self._conn

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.conn.execute(query, params)

    def fetchall(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        cur = self.conn.execute(query, params)
        cols = [desc.name for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetchone(self, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        cur = self.conn.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [desc.name for desc in cur.description]
        return dict(zip(cols, row))

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            log.info("database connection closed")

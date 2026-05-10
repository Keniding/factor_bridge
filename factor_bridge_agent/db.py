"""
Pool de conexiones PostgreSQL (Supabase).
Se inicializa perezosamente al primer uso.
POSTGRES_URL debe estar configurado; sin el el agente no puede operar.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2 import pool

_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        url = os.environ["POSTGRES_URL"]
        _pool = pool.SimpleConnectionPool(1, 5, dsn=url)
    return _pool


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)
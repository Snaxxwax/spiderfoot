# -*- coding: utf-8 -*-
"""Auth DB connection recovery.

Regression cover for: after a Postgres restart the cached psycopg2 connection
is dead, but libpq does not know it yet (``closed`` is 0, transaction status is
still IDLE), so every authenticated request failed with 401 "Invalid or expired
API key" until sf-api was restarted by hand.
"""
import psycopg2
import pytest
from psycopg2 import extensions as pg_ext

from spiderfoot.auth.models import AuthBackendUnavailable
from spiderfoot.auth.service import AuthService


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if self.conn.dead:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        self.conn.queries.append(sql)


class FakeConn:
    """Mimics the psycopg2 states observed against a real Postgres 15."""

    def __init__(self, dead=False, status=pg_ext.TRANSACTION_STATUS_IDLE):
        self.dead = dead
        self.closed = 0
        self.status = status
        self.queries = []
        self.rollbacks = 0
        self.autocommit = False

    def cursor(self):
        return FakeCursor(self)

    def get_transaction_status(self):
        return self.status

    def rollback(self):
        if self.dead:
            raise psycopg2.OperationalError("connection already gone")
        self.rollbacks += 1
        self.status = pg_ext.TRANSACTION_STATUS_IDLE

    def close(self):
        self.closed = 1


def test_live_idle_connection_is_reused():
    svc = AuthService()
    conn = FakeConn()
    svc._db_conn = conn
    assert svc._get_conn() is conn
    assert conn.queries == ["SELECT 1"], "should pre-ping an idle connection"


def test_dead_connection_is_replaced(monkeypatch):
    """The real bug: closed==0 and status IDLE, yet the socket is gone."""
    svc = AuthService()
    dead = FakeConn(dead=True)
    svc._db_conn = dead

    fresh = FakeConn()
    monkeypatch.setenv("SF_POSTGRES_DSN", "postgresql://x/y")
    monkeypatch.setattr(psycopg2, "connect", lambda dsn: fresh)

    assert svc._get_conn() is fresh, "must reconnect, not hand back the dead conn"
    assert dead.closed == 1, "dead connection should be closed, not leaked"


def test_aborted_transaction_is_recovered():
    """autocommit is off, so one failed query poisons the connection forever."""
    svc = AuthService()
    conn = FakeConn(status=pg_ext.TRANSACTION_STATUS_INERROR)
    svc._db_conn = conn
    assert svc._get_conn() is conn
    assert conn.rollbacks == 1, "aborted tx is only escapable via rollback"


def test_in_flight_transaction_is_not_disturbed():
    """Never roll back or ping a live transaction: that would drop writes."""
    svc = AuthService()
    conn = FakeConn(status=pg_ext.TRANSACTION_STATUS_INTRANS)
    svc._db_conn = conn
    assert svc._get_conn() is conn
    assert conn.rollbacks == 0 and conn.queries == []


def test_unreachable_db_raises_backend_unavailable(monkeypatch):
    """Must not be a generic error: the middleware maps this to 503, not 401."""
    svc = AuthService()
    monkeypatch.setenv("SF_POSTGRES_DSN", "postgresql://x/y")

    def boom(dsn):
        raise psycopg2.OperationalError("could not connect to server")

    monkeypatch.setattr(psycopg2, "connect", boom)
    with pytest.raises(AuthBackendUnavailable):
        svc._get_conn()


def test_mid_query_failure_surfaces_as_backend_unavailable(monkeypatch):
    """Postgres dying *during* validation must not read as a bad credential."""
    svc = AuthService()

    def boom(_raw):
        raise psycopg2.OperationalError("terminating connection due to shutdown")

    monkeypatch.setattr(svc, "validate_api_key", boom)
    with pytest.raises(AuthBackendUnavailable):
        svc.api_key_to_user_context("sf_whatever")


def test_genuinely_bad_key_still_raises_value_error(monkeypatch):
    """The 503 path must not swallow real authentication failures."""
    svc = AuthService()
    monkeypatch.setattr(svc, "validate_api_key", lambda _raw: None)
    with pytest.raises(ValueError):
        svc.api_key_to_user_context("sf_bogus")

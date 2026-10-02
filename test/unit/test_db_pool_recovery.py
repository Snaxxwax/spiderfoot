# -*- coding: utf-8 -*-
"""Pooled connection recovery in DbCore.

Regression cover for: psycopg2's ThreadedConnectionPool does not validate on
getconn(), so after a Postgres restart the first request got a dead socket and
failed with 500 "Failed to create DB handle: ... cursor already closed" from
inside SpiderFootDb's schema setup.
"""
import psycopg2
import pytest
from psycopg2 import extensions as pg_ext

from spiderfoot.db.db_core import DbCore


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


class FakeConn:
    def __init__(self, dead=False, status=pg_ext.TRANSACTION_STATUS_IDLE):
        self.dead = dead
        self.closed = 0
        self.status = status
        self.rollbacks = 0

    def cursor(self, **kw):
        return FakeCursor(self)

    def get_transaction_status(self):
        return self.status

    def rollback(self):
        if self.dead:
            raise psycopg2.OperationalError("connection already gone")
        self.rollbacks += 1
        self.status = pg_ext.TRANSACTION_STATUS_IDLE


class FakePool:
    """Mimics psycopg2's pool: hands back whatever it cached, unvalidated."""

    def __init__(self, conns):
        self.queue = list(conns)
        self.discarded = []
        self.returned = []

    def getconn(self):
        return self.queue.pop(0)

    def putconn(self, conn, close=False):
        (self.discarded if close else self.returned).append(conn)


def test_live_connection_is_returned_as_is():
    good = FakeConn()
    pool = FakePool([good])
    assert DbCore._checkout_live_conn(pool) is good
    assert pool.discarded == []


def test_dead_pooled_connections_are_discarded_and_replaced():
    """The real bug: closed==0 and status IDLE, but the socket is gone."""
    dead1, dead2, good = FakeConn(dead=True), FakeConn(dead=True), FakeConn()
    pool = FakePool([dead1, dead2, good])

    assert DbCore._checkout_live_conn(pool) is good
    assert pool.discarded == [dead1, dead2], "dead conns must be dropped from the pool"
    assert pool.returned == [], "a dead conn must not be recycled for the next caller"


def test_dirty_connection_is_rolled_back_before_reuse():
    dirty = FakeConn(status=pg_ext.TRANSACTION_STATUS_INERROR)
    pool = FakePool([dirty])
    assert DbCore._checkout_live_conn(pool) is dirty
    assert dirty.rollbacks == 1, "aborted tx is only escapable via rollback"


def test_gives_up_after_bounded_attempts():
    """Must raise, not loop forever, when Postgres is genuinely down."""
    deads = [FakeConn(dead=True) for _ in range(10)]
    pool = FakePool(deads)
    with pytest.raises(psycopg2.OperationalError):
        DbCore._checkout_live_conn(pool, attempts=3)
    assert len(pool.discarded) == 3, "should stop at the attempt limit"

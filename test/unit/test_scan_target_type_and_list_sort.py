"""Explicit scan target types, scan-list sorting, and the pagination clamp fix.

Three fixes live here:

* ``resolve_scan_target`` lets a caller name the target TYPE, which is the only way to
  scan a bare username through the API (the string-inference path cannot: it types an
  unquoted handle INTERNET_NAME and a quoted one keeps its quotes in every module URL).
* ``GET /scans`` now honours ``sort_by``/``sort_order`` instead of silently ignoring them.
* ``paginate`` slices from the clamped page, so a page past the end returns that last page
  rather than an empty slice mislabelled as page 1.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spiderfoot.api.routers.scan import router, resolve_scan_target
from spiderfoot.api.pagination import make_params, paginate
from spiderfoot.api.dependencies import get_api_key, get_scan_service, get_app_config
from test.unit.utils.fake_scan_service import FakeScanService, FakeScanRecord


class TestResolveScanTarget:
    def test_explicit_username_is_used_verbatim(self):
        # The case the inferrer cannot handle: a bare handle typed as a username.
        assert resolve_scan_target("Snaxxwax", "USERNAME") == ("Snaxxwax", "USERNAME")

    def test_explicit_username_strips_surrounding_quotes(self):
        # A quoted handle must NOT carry its quotes into module URLs.
        assert resolve_scan_target('"Snaxxwax"', "USERNAME") == ("Snaxxwax", "USERNAME")
        assert resolve_scan_target("'Snaxxwax'", "username") == ("Snaxxwax", "USERNAME")

    def test_explicit_type_is_normalized(self):
        assert resolve_scan_target("a@b.com", " emailaddr ")[1] == "EMAILADDR"

    def test_unknown_explicit_type_is_422(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            resolve_scan_target("x", "NOT_A_TYPE")
        assert exc.value.status_code == 422

    def test_empty_after_quote_strip_is_422(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            resolve_scan_target('""', "USERNAME")
        assert exc.value.status_code == 422

    def test_inference_unchanged_without_a_type(self):
        # Documents the behaviour the explicit path exists to route around.
        assert resolve_scan_target("a@b.com", None)[1] == "EMAILADDR"
        assert resolve_scan_target("Snaxxwax", None)[1] == "INTERNET_NAME"


class _SortableRecord(FakeScanRecord):
    def __init__(self, scan_id, created, **kw):
        super().__init__(scan_id, **kw)
        self.created = created

    def to_dict(self):
        d = super().to_dict()
        d["created"] = self.created
        return d


@pytest.fixture
def client():
    svc = FakeScanService()
    for sid, created in [("a", 300.0), ("b", 100.0), ("c", 200.0)]:
        svc.add_scan(_SortableRecord(sid, created, name=sid, target="example.com"))
    app = FastAPI()
    app.dependency_overrides[get_api_key] = lambda: "k"
    app.dependency_overrides[get_scan_service] = lambda: svc
    app.dependency_overrides[get_app_config] = lambda: type(
        "C", (), {"get_config": lambda self: {}}
    )()
    app.include_router(router)
    return TestClient(app)


class TestListSort:
    def test_sort_created_desc(self, client):
        ids = [s["scan_id"] for s in client.get(
            "/scans", params={"sort_by": "created", "sort_order": "desc"}
        ).json()["items"]]
        assert ids == ["a", "c", "b"]

    def test_sort_created_asc(self, client):
        ids = [s["scan_id"] for s in client.get(
            "/scans", params={"sort_by": "created", "sort_order": "asc"}
        ).json()["items"]]
        assert ids == ["b", "c", "a"]

    def test_unknown_sort_field_does_not_error(self, client):
        assert client.get("/scans", params={"sort_by": "bogus"}).status_code == 200


class TestPaginationClamp:
    def test_page_past_end_returns_last_page(self):
        got = paginate(list(range(5)), make_params(page=9, page_size=2))
        assert got["pages"] == 3
        assert got["page"] == 3
        assert got["items"] == [4]  # the real last page, not an empty slice

    def test_in_range_page_unchanged(self):
        got = paginate(list(range(5)), make_params(page=2, page_size=2))
        assert got["page"] == 2
        assert got["items"] == [2, 3]

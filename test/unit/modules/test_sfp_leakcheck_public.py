"""sfp_leakcheck falls back to the free public API without a usable API plan."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from modules.sfp_leakcheck import sfp_leakcheck
from spiderfoot import SpiderFootEvent

PUBLIC = json.dumps({"success": True, "found": 2, "fields": ["password"],
                     "sources": [{"name": "Example.com", "date": "2020-06"}, {"name": "Other.net", "date": ""}]})


def _run(api_key, responses):
    m = sfp_leakcheck()
    m.__name__ = "sfp_leakcheck"
    m.setup(MagicMock(), {"api_key": api_key, "pause": 0, "_useragent": "x"})
    urls = []

    def fetch(url, **kw):
        urls.append(url)
        return responses.pop(0)
    m.fetch_url = fetch
    m.error = m.info = MagicMock()
    got = []
    m.notifyListeners = got.append
    root = SpiderFootEvent("ROOT", "a@example.com", "", None)
    m.handleEvent(SpiderFootEvent("EMAILADDR", "a@example.com", "test", root))
    return urls, [(e.eventType, e.data) for e in got]


def test_no_key_uses_public_api():
    urls, ev = _run("", [{"code": "200", "content": PUBLIC}])
    assert urls == ["https://leakcheck.io/api/public?check=a@example.com"]
    assert ev[:2] == [("EMAILADDR_COMPROMISED", "a@example.com [Example.com - 2020-06]"),
                      ("EMAILADDR_COMPROMISED", "a@example.com [Other.net - Unknown Date]")]
    assert ev[2][0] == "RAW_RIR_DATA"


def test_key_without_api_plan_falls_back_and_stays_public():
    urls, ev = _run("k", [{"code": "403", "content": "{}"}, {"code": "200", "content": PUBLIC}])
    assert "/api/v2/" in urls[0] and "/api/public" in urls[1]
    assert len([t for t, _ in ev if t == "EMAILADDR_COMPROMISED"]) == 2


def test_public_not_found_is_silent():
    _, ev = _run("", [{"code": "200", "content": json.dumps({"success": False, "error": "Not found"})}])
    assert ev == []

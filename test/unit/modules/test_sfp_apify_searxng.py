from __future__ import annotations

"""Tests for the sfp_apify_* and sfp_searxng modules with stubbed responses."""

import json
from unittest.mock import MagicMock

import pytest

from modules import sfp_apify_google, sfp_apify_instagram, sfp_apify_reddit, sfp_apify_tiktok
from modules.sfp_searxng import sfp_searxng
from spiderfoot import SpiderFootEvent


def _run(module_cls, data, event_type="USERNAME", opts=None):
    m = module_cls()
    m.__name__ = module_cls.__name__
    m.setup(MagicMock(), {"api_key": "t", **(opts or {})})
    got = []
    m.notifyListeners = got.append
    m.error = MagicMock()
    root = SpiderFootEvent("ROOT", data, "", None)
    m.handleEvent(SpiderFootEvent(event_type, data, "test", root))
    return m, [(e.eventType, e.data) for e in got]


@pytest.fixture
def actor(monkeypatch):
    calls = []

    def stub(items):
        def fake(module, actor_id, run_input):
            calls.append((actor_id, run_input))
            return items
        for mod in (sfp_apify_google, sfp_apify_instagram, sfp_apify_reddit, sfp_apify_tiktok):
            monkeypatch.setattr(mod, "run_actor", fake)
        return calls
    return stub


def test_opts_have_descriptions():
    for cls in (sfp_apify_instagram.sfp_apify_instagram, sfp_apify_tiktok.sfp_apify_tiktok,
                sfp_apify_reddit.sfp_apify_reddit, sfp_apify_google.sfp_apify_google, sfp_searxng):
        assert cls().opts.keys() == cls().optdescs.keys()


def test_instagram_ignores_other_usernames(actor):
    actor([{"username": "someoneelse", "url": "https://www.instagram.com/someoneelse/"},
           {"username": "Snaxxwax", "url": "https://www.instagram.com/snaxxwax/", "externalUrl": "https://ex.com"}])
    _, ev = _run(sfp_apify_instagram.sfp_apify_instagram, "snaxxwax")
    assert [t for t, _ in ev] == ["SOCIAL_MEDIA", "LINKED_URL_EXTERNAL", "RAW_RIR_DATA"]
    assert ev[0][1] == "Instagram: <SFURL>https://www.instagram.com/snaxxwax/</SFURL>"


def test_tiktok_one_profile_from_video_rows(actor):
    actor([{"authorMeta": {"name": "snaxxwax"}, "webVideoUrl": "https://tiktok.com/v/1"},
           {"authorMeta": {"name": "snaxxwax"}, "webVideoUrl": "https://tiktok.com/v/2"}])
    _, ev = _run(sfp_apify_tiktok.sfp_apify_tiktok, "Snaxxwax")
    assert ev[0] == ("SOCIAL_MEDIA", "TikTok: <SFURL>https://www.tiktok.com/@Snaxxwax</SFURL>")
    assert json.loads(ev[1][1])["videos"] == ["https://tiktok.com/v/1", "https://tiktok.com/v/2"]


def test_reddit_profile_with_activity(actor):
    actor([{"dataType": "user_profile", "username": "spez", "profileUrl": "https://www.reddit.com/user/spez/"},
           {"dataType": "comment", "url": "https://www.reddit.com/r/x/1", "communityName": "x"}])
    _, ev = _run(sfp_apify_reddit.sfp_apify_reddit, "u/spez")
    assert ev[0] == ("SOCIAL_MEDIA", "Reddit: <SFURL>https://www.reddit.com/user/spez/</SFURL>")
    assert json.loads(ev[1][1])["activity"] == [{"dataType": "comment", "url": "https://www.reddit.com/r/x/1",
                                                 "communityName": "x"}]


def test_reddit_absent_user_emits_nothing(actor):
    actor([])
    assert _run(sfp_apify_reddit.sfp_apify_reddit, "nobody_zz")[1] == []


def test_google_quotes_the_query_and_caps_runs(actor):
    calls = actor([{"organicResults": [{"url": "https://a.example", "title": "A", "description": "d"}]}])
    m, ev = _run(sfp_apify_google.sfp_apify_google, "someone@example.com", "EMAILADDR", {"max_queries": 1})
    assert calls[0][1]["queries"] == '"someone@example.com"'
    assert ev == [("LINKED_URL_EXTERNAL", "https://a.example"), ("SEARCH_ENGINE_WEB_CONTENT", "A\nhttps://a.example\nd")]
    m.handleEvent(SpiderFootEvent("USERNAME", "other", "test", SpiderFootEvent("ROOT", "x", "", None)))
    assert len(calls) == 1


def test_searxng_parses_json_results():
    m = sfp_searxng()
    m.__name__ = "sfp_searxng"
    sf = MagicMock()
    sf.fetchUrl.return_value = {"code": "200", "content": json.dumps(
        {"results": [{"url": "https://b.example", "title": "B", "content": "c"}, {"title": "no url"}]})}
    m.setup(sf, {})
    got = []
    m.notifyListeners = got.append
    m.handleEvent(SpiderFootEvent("USERNAME", "Snaxxwax", "test", SpiderFootEvent("ROOT", "x", "", None)))
    assert "q=%22Snaxxwax%22" in sf.fetchUrl.call_args[0][0]
    assert [(e.eventType, e.data) for e in got] == [
        ("LINKED_URL_EXTERNAL", "https://b.example"), ("SEARCH_ENGINE_WEB_CONTENT", "B\nhttps://b.example\nc")]

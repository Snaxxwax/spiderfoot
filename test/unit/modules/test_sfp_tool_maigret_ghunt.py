from __future__ import annotations

"""Tests for sfp_tool_maigret and sfp_tool_ghunt output parsing and input guards."""

import json

from modules.sfp_tool_ghunt import sfp_tool_ghunt
from modules.sfp_tool_maigret import _USERNAME_RE, sfp_tool_maigret

# Trimmed from a real maigret 0.6.6 `--json simple` report.
MAIGRET_REPORT = {
    "GitHub": {
        "url_user": "https://github.com/Snaxxwax",
        "http_status": 200,
        "is_similar": False,
        "site": {"tags": ["coding"], "checkType": "status_code"},
        "status": {"status": "Claimed", "tags": ["coding"], "ids": {"uid": "105263527"}},
    },
    "LoginWall": {
        "url_user": "https://example.com/Snaxxwax",
        "http_status": 403,
        "status": {"status": "Claimed", "tags": []},
    },
    "Absent": {"url_user": "https://x.example/Snaxxwax", "status": {"status": "Available"}},
}

# Trimmed from a real ghunt 2.3.4 `email --json` report.
GHUNT_REPORT = {
    "PROFILE_CONTAINER": {
        "profile": {
            "personId": "114322781164246389229",
            "names": {},
            "profilePhotos": {"PROFILE": {"url": "https://lh3.googleusercontent.com/a-/x", "isDefault": False}},
        },
        "maps": {"photos": None, "reviews": None, "stats": {}},
    }
}


def test_opts_have_descriptions():
    for module in (sfp_tool_maigret(), sfp_tool_ghunt()):
        assert module.opts.keys() == module.optdescs.keys()


def test_maigret_report_parsing():
    found = sfp_tool_maigret().parseReport(MAIGRET_REPORT)
    assert found == [
        ("ACCOUNT_EXTERNAL_OWNED", "GitHub (Category: coding)\n<SFURL>https://github.com/Snaxxwax</SFURL>",
         {"uid": "105263527"}),
        ("SIMILAR_ACCOUNT_EXTERNAL", "LoginWall (Category: unknown)\n<SFURL>https://example.com/Snaxxwax</SFURL>", {}),
    ]


def test_maigret_refuses_option_like_usernames():
    assert _USERNAME_RE.match("Snaxxwax")
    for bad in ("-h", "--all-sites", "../etc", "a b", "a/b", ""):
        assert not _USERNAME_RE.match(bad)


def test_maigret_command_never_recurses_or_autoupdates():
    module = sfp_tool_maigret()
    argv = module.buildCommand("maigret", "Snaxxwax", "/tmp/x")
    assert argv[:2] == ["maigret", "Snaxxwax"]
    assert "--no-recursion" in argv and "--no-autoupdate" in argv
    module.opts = dict(module.opts, top_sites=0)
    assert "--all-sites" in module.buildCommand("maigret", "Snaxxwax", "/tmp/x")


def test_ghunt_report_parsing():
    found = sfp_tool_ghunt().parseReport(GHUNT_REPORT)
    assert found[0] == ("ACCOUNT_EXTERNAL_OWNED",
                        "Google (Category: google)\n<SFURL>https://www.google.com/maps/contrib/114322781164246389229</SFURL>")
    assert [t for t, _ in found] == ["ACCOUNT_EXTERNAL_OWNED", "RAW_RIR_DATA"]  # empty names -> no HUMAN_NAME
    assert json.loads(found[1][1])["profile"]["personId"] == "114322781164246389229"


def test_ghunt_skips_containers_without_an_account():
    assert sfp_tool_ghunt().parseReport({"X": {"profile": {}}, "Y": None}) == []

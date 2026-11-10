from __future__ import annotations

"""SpiderFoot plug-in module: apify_tiktok."""

import json
import re

from spiderfoot import SpiderFootEvent
from spiderfoot.apify_actor import run_actor
from spiderfoot.plugins.async_plugin import SpiderFootAsyncPlugin

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{2,24}$")


class sfp_apify_tiktok(SpiderFootAsyncPlugin):

    """Look up a TikTok profile and its recent videos by username through Apify's TikTok Profile Scraper."""

    meta = {
        'name': "Apify - TikTok",
        'summary': "Look up a TikTok profile and its recent videos by username through Apify's TikTok Profile Scraper.",
        'flags': ["apikey"],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://apify.com/clockworks/tiktok-profile-scraper",
            'model': "COMMERCIAL_ONLY",
            'references': ["https://docs.apify.com/api/v2"],
            'apiKeyInstructions': "Sign up at https://apify.com. Go to Settings > API & Integrations. Copy your personal API token.",
            'description': "Runs on Apify's infrastructure and proxies, so TikTok never sees this host.",
        },
    }

    opts = {
        'api_key': "",
        'max_charge_usd': 0.10,
        'run_timeout': 290,
        'max_videos': 10,
    }

    optdescs = {
        'api_key': "Apify API token.",
        'max_charge_usd': "Maximum Apify charge per lookup, in USD.",
        'run_timeout': "Maximum seconds to wait for one Actor run (Apify caps this at 300).",
        'max_videos': "Recent videos to fetch per profile.",
    }

    results = None
    errorState = False

    def setup(self, sfc: SpiderFoot, userOpts: dict = None) -> None:
        """Set up the module."""
        super().setup(sfc, userOpts or {})
        self.results = self.tempStorage()
        self.errorState = False

    def watchedEvents(self) -> list:
        """Return the list of events this module watches."""
        return ["USERNAME"]

    def producedEvents(self) -> list:
        """Return the list of events this module produces."""
        return ["SOCIAL_MEDIA", "RAW_RIR_DATA"]

    def handleEvent(self, event: SpiderFootEvent) -> None:
        """Handle an event received by this module."""
        username = event.data.strip().lstrip("@")
        if self.errorState or username.lower() in self.results:
            return
        self.results[username.lower()] = True
        if not _USERNAME_RE.match(username):
            return

        items = run_actor(self, "clockworks~tiktok-profile-scraper", {
            "profiles": [username],
            "resultsPerPage": int(self.opts['max_videos']),
            "profileScrapeSections": ["videos"],
        })
        # One row per video, each repeating the author.
        rows = [i for i in items or [] if str((i.get("authorMeta") or {}).get("name", "")).lower() == username.lower()]
        if not rows:
            return
        author = rows[0]["authorMeta"]
        url = author.get("profileUrl") or f"https://www.tiktok.com/@{username}"
        profile = SpiderFootEvent("SOCIAL_MEDIA", f"TikTok: <SFURL>{url}</SFURL>", self.__name__, event)
        self.notifyListeners(profile)
        summary = {**author, "videos": [r.get("webVideoUrl") for r in rows if r.get("webVideoUrl")]}
        self.notifyListeners(SpiderFootEvent("RAW_RIR_DATA", json.dumps(summary, sort_keys=True, default=str), self.__name__, profile))

# End of sfp_apify_tiktok class

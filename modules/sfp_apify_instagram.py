from __future__ import annotations

"""SpiderFoot plug-in module: apify_instagram."""

import json
import re

from spiderfoot import SpiderFootEvent
from spiderfoot.apify_actor import run_actor
from spiderfoot.plugins.async_plugin import SpiderFootAsyncPlugin

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


class sfp_apify_instagram(SpiderFootAsyncPlugin):

    """Look up an Instagram profile by username through Apify's Instagram Profile Scraper."""

    meta = {
        'name': "Apify - Instagram",
        'summary': "Look up an Instagram profile by username through Apify's Instagram Profile Scraper.",
        'flags': ["apikey"],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://apify.com/apify/instagram-profile-scraper",
            'model': "COMMERCIAL_ONLY",
            'references': ["https://docs.apify.com/api/v2"],
            'apiKeyInstructions': "Sign up at https://apify.com. Go to Settings > API & Integrations. Copy your personal API token.",
            'description': "Runs on Apify's infrastructure and proxies, so Instagram never sees this host.",
        },
    }

    opts = {
        'api_key': "",
        'max_charge_usd': 0.05,
        'run_timeout': 290,
    }

    optdescs = {
        'api_key': "Apify API token.",
        'max_charge_usd': "Maximum Apify charge per lookup, in USD.",
        'run_timeout': "Maximum seconds to wait for one Actor run (Apify caps this at 300).",
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
        return ["SOCIAL_MEDIA", "LINKED_URL_EXTERNAL", "RAW_RIR_DATA"]

    def handleEvent(self, event: SpiderFootEvent) -> None:
        """Handle an event received by this module."""
        username = event.data.strip().lstrip("@")
        if self.errorState or username.lower() in self.results:
            return
        self.results[username.lower()] = True
        if not _USERNAME_RE.match(username):
            return

        items = run_actor(self, "apify~instagram-profile-scraper",
                          {"usernames": [username], "includeAboutSection": True})
        for item in items or []:
            if str(item.get("username", "")).lower() != username.lower():
                continue
            url = item.get("url") or f"https://www.instagram.com/{username}/"
            profile = SpiderFootEvent("SOCIAL_MEDIA", f"Instagram: <SFURL>{url}</SFURL>", self.__name__, event)
            self.notifyListeners(profile)
            if item.get("externalUrl"):
                self.notifyListeners(SpiderFootEvent("LINKED_URL_EXTERNAL", item["externalUrl"], self.__name__, profile))
            self.notifyListeners(SpiderFootEvent("RAW_RIR_DATA", json.dumps(item, sort_keys=True, default=str), self.__name__, profile))

# End of sfp_apify_instagram class

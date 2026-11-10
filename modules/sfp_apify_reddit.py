from __future__ import annotations

"""SpiderFoot plug-in module: apify_reddit."""

import json
import re

from spiderfoot import SpiderFootEvent
from spiderfoot.apify_actor import run_actor
from spiderfoot.plugins.async_plugin import SpiderFootAsyncPlugin

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")


class sfp_apify_reddit(SpiderFootAsyncPlugin):

    """Look up a Reddit user's profile and recent posts and comments through Apify's Reddit User Scraper."""

    meta = {
        'name': "Apify - Reddit",
        'summary': "Look up a Reddit user's profile and recent posts and comments through Apify's Reddit User Scraper.",
        'flags': ["apikey"],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://apify.com/harshmaur/reddit-user-scraper",
            'model': "COMMERCIAL_ONLY",
            'references': ["https://docs.apify.com/api/v2"],
            'apiKeyInstructions': "Sign up at https://apify.com. Go to Settings > API & Integrations. Copy your personal API token.",
            'description': "Runs on Apify's infrastructure and proxies, so Reddit never sees this host.",
        },
    }

    opts = {
        'api_key': "",
        'max_charge_usd': 0.10,
        'run_timeout': 290,
        'max_posts': 20,
        'max_comments': 20,
    }

    optdescs = {
        'api_key': "Apify API token.",
        'max_charge_usd': "Maximum Apify charge per lookup, in USD.",
        'run_timeout': "Maximum seconds to wait for one Actor run (Apify caps this at 300).",
        'max_posts': "Recent posts to fetch per user.",
        'max_comments': "Recent comments to fetch per user.",
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
        username = event.data.strip()
        if username.lower().startswith("u/"):
            username = username[2:]
        if self.errorState or username.lower() in self.results:
            return
        self.results[username.lower()] = True
        if not _USERNAME_RE.match(username):
            return

        items = run_actor(self, "harshmaur~reddit-user-scraper", {
            "usernames": [username],
            "maxPostsCount": int(self.opts['max_posts']),
            "maxCommentsCount": int(self.opts['max_comments']),
        })
        items = items or []
        profiles = [i for i in items if i.get("dataType") == "user_profile"
                    and str(i.get("username", "")).lower() == username.lower()]
        if not profiles:
            return
        prof = profiles[0]
        url = prof.get("profileUrl") or f"https://www.reddit.com/user/{username}/"
        profile = SpiderFootEvent("SOCIAL_MEDIA", f"Reddit: <SFURL>{url}</SFURL>", self.__name__, event)
        self.notifyListeners(profile)
        activity = [
            {k: i.get(k) for k in ("dataType", "url", "communityName", "createdAt", "commentCreatedAt", "title")
             if i.get(k)}
            for i in items if i.get("dataType") in ("post", "comment")
        ]
        self.notifyListeners(SpiderFootEvent(
            "RAW_RIR_DATA", json.dumps({**prof, "activity": activity}, sort_keys=True, default=str),
            self.__name__, profile))

# End of sfp_apify_reddit class

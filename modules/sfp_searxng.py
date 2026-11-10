from __future__ import annotations

"""SpiderFoot plug-in module: searxng."""

import json
import urllib.parse

from spiderfoot import SpiderFootEvent
from spiderfoot.plugins.async_plugin import SpiderFootAsyncPlugin


class sfp_searxng(SpiderFootAsyncPlugin):

    """Search a self-hosted SearXNG instance for an email address, username or name."""

    meta = {
        'name': "SearXNG",
        'summary': "Search a self-hosted SearXNG metasearch instance for an email address, username or name.",
        'flags': [],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["Search Engines"],
        'dataSource': {
            'website': "https://docs.searxng.org/",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': ["https://docs.searxng.org/dev/search_api.html"],
            'description': "Your own SearXNG instance; its JSON output format must be enabled.",
        },
    }

    opts = {
        'searxng_url': "http://searxng:8080",
        'max_queries': 10,
        'max_results': 20,
    }

    optdescs = {
        'searxng_url': "Base URL of the SearXNG instance.",
        'max_queries': "Maximum searches per scan.",
        'max_results': "Maximum results kept per search.",
    }

    results = None
    errorState = False

    def setup(self, sfc: SpiderFoot, userOpts: dict = None) -> None:
        """Set up the module."""
        super().setup(sfc, userOpts or {})
        self.results = self.tempStorage()
        self.errorState = False
        self.queries = 0

    def watchedEvents(self) -> list:
        """Return the list of events this module watches."""
        return ["EMAILADDR", "USERNAME", "HUMAN_NAME"]

    def producedEvents(self) -> list:
        """Return the list of events this module produces."""
        return ["LINKED_URL_EXTERNAL", "SEARCH_ENGINE_WEB_CONTENT"]

    def handleEvent(self, event: SpiderFootEvent) -> None:
        """Handle an event received by this module."""
        term = event.data.strip()
        if self.errorState or not term or "\n" in term or term.lower() in self.results:
            return
        self.results[term.lower()] = True
        if self.queries >= int(self.opts['max_queries']):
            self.debug(f"Skipping {term}: max_queries reached.")
            return
        self.queries += 1

        query = urllib.parse.urlencode({"q": f'"{term}"', "format": "json"})
        res = self.sf.fetchUrl(f"{self.opts['searxng_url'].rstrip('/')}/search?{query}",
                               timeout=30, useragent=self.opts.get('_useragent', "SpiderFoot"))
        if str(res.get("code")) != "200":
            self.error(f"SearXNG returned HTTP {res.get('code')}; is format=json enabled?")
            if res.get("code") is None:
                self.errorState = True  # unreachable: do not retry for every event
            return
        try:
            hits = json.loads(res["content"]).get("results") or []
        except (ValueError, AttributeError):
            self.error("SearXNG returned invalid JSON.")
            return

        for hit in hits[:int(self.opts['max_results'])]:
            url = hit.get("url") if isinstance(hit, dict) else None
            if not url:
                continue
            link = SpiderFootEvent("LINKED_URL_EXTERNAL", url, self.__name__, event)
            self.notifyListeners(link)
            text = "\n".join(s for s in (hit.get("title"), url, hit.get("content")) if s)
            self.notifyListeners(SpiderFootEvent("SEARCH_ENGINE_WEB_CONTENT", text, self.__name__, link))

# End of sfp_searxng class

from __future__ import annotations

"""SpiderFoot plug-in module: apify_google."""

from spiderfoot import SpiderFootEvent
from spiderfoot.apify_actor import run_actor
from spiderfoot.plugins.async_plugin import SpiderFootAsyncPlugin


class sfp_apify_google(SpiderFootAsyncPlugin):

    """Search Google for an email address, username or name through Apify's Google Search Scraper."""

    meta = {
        'name': "Apify - Google Search",
        'summary': "Search Google for an email address, username or name through Apify's Google Search Scraper.",
        'flags': ["apikey"],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["Search Engines"],
        'dataSource': {
            'website': "https://apify.com/apify/google-search-scraper",
            'model': "COMMERCIAL_ONLY",
            'references': ["https://docs.apify.com/api/v2"],
            'apiKeyInstructions': "Sign up at https://apify.com. Go to Settings > API & Integrations. Copy your personal API token.",
            'description': "Runs on Apify's infrastructure and proxies, so Google never sees this host.",
        },
    }

    opts = {
        'api_key': "",
        'max_charge_usd': 0.50,
        'run_timeout': 290,
        'max_queries': 5,
    }

    optdescs = {
        'api_key': "Apify API token.",
        'max_charge_usd': "Maximum Apify charge per search, in USD.",
        'run_timeout': "Maximum seconds to wait for one Actor run (Apify caps this at 300).",
        'max_queries': "Maximum searches per scan (each one is a paid Actor run).",
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

        pages = run_actor(self, "apify~google-search-scraper",
                          {"queries": f'"{term}"', "maxPagesPerQuery": 1})
        for page in pages or []:
            for hit in page.get("organicResults") or []:
                url = hit.get("url") if isinstance(hit, dict) else None
                if not url:
                    continue
                link = SpiderFootEvent("LINKED_URL_EXTERNAL", url, self.__name__, event)
                self.notifyListeners(link)
                text = "\n".join(s for s in (hit.get("title"), url, hit.get("description")) if s)
                self.notifyListeners(SpiderFootEvent("SEARCH_ENGINE_WEB_CONTENT", text, self.__name__, link))

# End of sfp_apify_google class

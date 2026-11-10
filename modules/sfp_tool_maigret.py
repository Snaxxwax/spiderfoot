from __future__ import annotations

"""SpiderFoot plug-in module: tool_maigret."""

# -------------------------------------------------------------------------------
# Name:         sfp_tool_maigret
# Purpose:      Find accounts by username across thousands of sites using a local
#               Maigret installation.
#               Tool: https://github.com/soxoj/maigret
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import os
import re
import tempfile
from pathlib import Path
from shutil import which
from subprocess import PIPE, Popen, TimeoutExpired

from spiderfoot import SpiderFootEvent
from spiderfoot.plugins.async_plugin import SpiderFootAsyncPlugin

# Maigret takes the username as a positional argument, so anything that could read as an
# option or a path is refused before it reaches argv.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class sfp_tool_maigret(SpiderFootAsyncPlugin):

    """Find accounts by username across thousands of sites using a local Maigret installation."""

    meta = {
        'name': "Tool - Maigret",
        'summary': "Find accounts by username across thousands of sites using a local Maigret installation.",
        'flags': ["tool", "slow"],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["Social Media"],
        'toolDetails': {
            'name': "Maigret",
            'description': "Maigret collects a dossier on a person by username only, checking "
            "for accounts on a huge number of sites and gathering all the available "
            "information from web pages.",
            'website': 'https://github.com/soxoj/maigret',
            'repository': 'https://github.com/soxoj/maigret'
        },
    }

    opts = {
        'maigretpath': "maigret",
        'top_sites': 500,
        'site_timeout': 15,
        'run_timeout': 900,
        'max_connections': 16,
        'retries': 1,
    }

    optdescs = {
        'maigretpath': "Path to the maigret executable. If just 'maigret' then it must be in your PATH.",
        'top_sites': "Check only the N highest-ranked sites. 0 = all sites (3000+, much slower).",
        'site_timeout': "Per-site request timeout in seconds.",
        'run_timeout': "Maximum seconds one Maigret run may take before it is killed.",
        'max_connections': "Maximum concurrent connections Maigret opens.",
        'retries': "Retries for failed site checks.",
    }

    results = None
    errorState = False

    def setup(self, sfc: SpiderFoot, userOpts: dict = None) -> None:
        """Set up the module."""
        super().setup(sfc, userOpts or {})
        self.results = self.tempStorage()
        self.errorState = False
        self.__dataSource__ = "Maigret"

    def watchedEvents(self) -> list:
        """Return the list of events this module watches."""
        return ["USERNAME"]

    def producedEvents(self) -> list:
        """Return the list of events this module produces."""
        return ["ACCOUNT_EXTERNAL_OWNED", "SIMILAR_ACCOUNT_EXTERNAL", "RAW_RIR_DATA"]

    def buildCommand(self, exe: str, username: str, outdir: str) -> list:
        """Return the argv for one Maigret run."""
        top = int(self.opts['top_sites'])
        return [
            exe, username,
            *(["--top-sites", str(top)] if top > 0 else ["--all-sites"]),
            "--json", "simple",
            "--folderoutput", outdir,
            "--no-color", "--no-progressbar",
            "--timeout", str(int(self.opts['site_timeout'])),
            "--retries", str(int(self.opts['retries'])),
            "--max-connections", str(int(self.opts['max_connections'])),
            # Pin the site list to the installed package: auto-update fetches from GitHub
            # mid-scan and would change a scan's breadth without the image changing.
            "--no-autoupdate",
            # Recursion would search usernames Maigret scraped off profiles, i.e. other
            # subjects. SpiderFoot's own event chain decides what gets scanned next.
            "--no-recursion",
        ]

    def parseReport(self, report: dict) -> list:
        """Turn Maigret's simple JSON report into (event type, data, ids) tuples."""
        found = []
        for sitename, site in report.items():
            if not isinstance(site, dict):
                continue
            status = site.get('status') or {}
            if status.get('status') != "Claimed":
                continue
            url = site.get('url_user') or status.get('url')
            if not url:
                continue
            tags = status.get('tags') or (site.get('site') or {}).get('tags') or []
            category = ", ".join(t for t in tags if isinstance(t, str)) or "unknown"
            http = site.get('http_status')
            # A "Claimed" verdict read off an error/login page, or Maigret's own near-miss
            # flag, is not evidence the exact handle exists there.
            weak = site.get('is_similar') or (isinstance(http, int) and not 200 <= http < 300)
            evt_type = "SIMILAR_ACCOUNT_EXTERNAL" if weak else "ACCOUNT_EXTERNAL_OWNED"
            data = f"{sitename} (Category: {category})\n<SFURL>{url}</SFURL>"
            ids = status.get('ids') if isinstance(status.get('ids'), dict) else {}
            found.append((evt_type, data, ids))
        return found

    def handleEvent(self, event: SpiderFootEvent) -> None:
        """Handle an event received by this module."""
        eventData = event.data

        self.debug(f"Received event, {event.eventType}, from {event.module}")

        if self.errorState:
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData} as already scanned.")
            return
        self.results[eventData] = True

        if not _USERNAME_RE.match(eventData):
            self.debug(f"Skipping {eventData}: not a plain username.")
            return

        exe = which(self.opts['maigretpath'])
        if not exe or not Path(exe).is_file():
            self.error(f"You enabled sfp_tool_maigret but {self.opts['maigretpath']} was not found.")
            self.errorState = True
            return

        with tempfile.TemporaryDirectory(prefix="sf-maigret-") as workdir:
            # Maigret writes its settings/cache under $HOME on startup; the worker's
            # home is read-only, so give each run its own scratch home.
            env = dict(os.environ, HOME=workdir)
            p = Popen(self.buildCommand(exe, eventData, workdir), stdout=PIPE, stderr=PIPE, env=env)
            try:
                _, stderr = p.communicate(timeout=int(self.opts['run_timeout']))
            except TimeoutExpired:
                p.kill()
                p.communicate()
                self.error(f"Maigret timed out on {eventData} after {self.opts['run_timeout']}s.")
                return

            report = Path(workdir) / f"report_{eventData}_simple.json"
            if p.returncode != 0 or not report.is_file():
                self.error(f"Maigret failed on {eventData}: {stderr.decode('utf-8', errors='replace')[-500:]}")
                return
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except Exception as e:
                self.error(f"Couldn't parse Maigret's JSON report: {e}")
                return

        for evt_type, evt_data, ids in self.parseReport(data):
            if self.checkForStop():
                return
            evt = SpiderFootEvent(evt_type, evt_data, self.__name__, event)
            self.notifyListeners(evt)
            if ids:
                self.notifyListeners(SpiderFootEvent("RAW_RIR_DATA", json.dumps(ids, sort_keys=True), self.__name__, evt))

# End of sfp_tool_maigret class

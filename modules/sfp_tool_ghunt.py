from __future__ import annotations

"""SpiderFoot plug-in module: tool_ghunt."""

# -------------------------------------------------------------------------------
# Name:         sfp_tool_ghunt
# Purpose:      Resolve the Google account behind an email address using a local
#               GHunt installation.
#               Tool: https://github.com/mxrch/GHunt
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from shutil import which
from subprocess import PIPE, Popen, TimeoutExpired

from spiderfoot import SpiderFootEvent
from spiderfoot.plugins.async_plugin import SpiderFootAsyncPlugin

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class sfp_tool_ghunt(SpiderFootAsyncPlugin):

    """Resolve the Google account behind an email address using a local GHunt installation."""

    meta = {
        'name': "Tool - GHunt",
        'summary': "Resolve the Google account (Gaia ID, profile photo, Maps contributions) "
        "behind an email address using a local GHunt installation.",
        'flags': ["tool", "apikey"],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["Social Media"],
        'toolDetails': {
            'name': "GHunt",
            'description': "GHunt is an offensive Google framework that resolves an email "
            "address to its Google account and the public data attached to it.",
            'website': 'https://github.com/mxrch/GHunt',
            'repository': 'https://github.com/mxrch/GHunt'
        },
        'dataSource': {
            'type': "tool",
            'model': "FREE_AUTH_UNLIMITED",
            'apiKeyInstructions': "GHunt authenticates as a Google account you own; use a dedicated one. Run `ghunt login` once to produce creds.m. Make that file readable by the scanner and set creds_path to it.",
        },
    }

    opts = {
        'ghuntpath': "ghunt",
        'creds_path': "/run/ghunt/.malfrats/ghunt/creds.m",
        'target_only': True,
        'max_lookups': 10,
        'run_timeout': 180,
    }

    optdescs = {
        'ghuntpath': "Path to the ghunt executable. If just 'ghunt' then it must be in your PATH.",
        'creds_path': "Path to the creds.m file produced by `ghunt login`.",
        'target_only': "Only look up the scan target itself, not addresses discovered during the scan "
        "(every lookup is made as your Google account).",
        'max_lookups': "Maximum GHunt lookups per scan.",
        'run_timeout': "Maximum seconds one GHunt lookup may take before it is killed.",
    }

    results = None
    errorState = False

    def setup(self, sfc: SpiderFoot, userOpts: dict = None) -> None:
        """Set up the module."""
        super().setup(sfc, userOpts or {})
        self.results = self.tempStorage()
        self.errorState = False
        self.lookups = 0
        self.__dataSource__ = "GHunt"

    def watchedEvents(self) -> list:
        """Return the list of events this module watches."""
        return ["EMAILADDR"]

    def producedEvents(self) -> list:
        """Return the list of events this module produces."""
        return ["ACCOUNT_EXTERNAL_OWNED", "HUMAN_NAME", "RAW_RIR_DATA"]

    def parseReport(self, report: dict) -> list:
        """Turn GHunt's JSON report into (event type, data) tuples."""
        found = []
        for container in report.values():
            if not isinstance(container, dict):
                continue
            profile = container.get('profile') or {}
            gaia = profile.get('personId')
            if not isinstance(gaia, str) or not gaia:
                continue
            found.append((
                "ACCOUNT_EXTERNAL_OWNED",
                f"Google (Category: google)\n<SFURL>https://www.google.com/maps/contrib/{gaia}</SFURL>",
            ))
            # GHunt 2.3.4 never fills names (Google removed them); kept for when it does.
            name = ((profile.get('names') or {}).get('PROFILE') or {}).get('fullname')
            if isinstance(name, str) and name.strip():
                found.append(("HUMAN_NAME", name.strip()))
            found.append(("RAW_RIR_DATA", json.dumps(container, sort_keys=True, default=str)))
        return found

    def handleEvent(self, event: SpiderFootEvent) -> None:
        """Handle an event received by this module."""
        eventData = event.data.strip().lower()

        self.debug(f"Received event, {event.eventType}, from {event.module}")

        if self.errorState:
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData} as already scanned.")
            return
        self.results[eventData] = True

        if self.opts['target_only'] and eventData != str(self.getTarget().targetValue).strip().lower():
            self.debug(f"Skipping {eventData}: not the scan target (target_only).")
            return

        if not _EMAIL_RE.match(eventData):
            self.debug(f"Skipping {eventData}: not a plain email address.")
            return

        if self.lookups >= int(self.opts['max_lookups']):
            self.debug(f"Skipping {eventData}: max_lookups reached.")
            return

        exe = which(self.opts['ghuntpath'])
        if not exe or not Path(exe).is_file():
            self.error(f"You enabled sfp_tool_ghunt but {self.opts['ghuntpath']} was not found.")
            self.errorState = True
            return

        creds = Path(self.opts['creds_path'])
        if not creds.is_file():
            self.error(f"GHunt credentials not found at {creds}; run `ghunt login` and set creds_path.")
            self.errorState = True
            return

        self.lookups += 1
        with tempfile.TemporaryDirectory(prefix="sf-ghunt-") as workdir:
            # GHunt reads $HOME/.malfrats/ghunt/creds.m with no override and may rewrite it,
            # so each run gets a private copy under a scratch home.
            home = Path(workdir) / "home"
            (home / ".malfrats" / "ghunt").mkdir(parents=True)
            shutil.copyfile(creds, home / ".malfrats" / "ghunt" / "creds.m")
            out = Path(workdir) / "ghunt.json"
            env = dict(os.environ, HOME=str(home))
            p = Popen([exe, "email", eventData, "--json", str(out)], stdout=PIPE, stderr=PIPE, env=env, cwd=workdir)
            try:
                stdout, stderr = p.communicate(timeout=int(self.opts['run_timeout']))
            except TimeoutExpired:
                p.kill()
                p.communicate()
                self.error(f"GHunt timed out on {eventData} after {self.opts['run_timeout']}s.")
                return

            if not out.is_file():
                # No Google account behind the address also ends here (GHunt exits non-zero
                # with "The target wasn't found."), which is a result, not an error.
                tail = (stdout + stderr).decode('utf-8', errors='replace')[-500:]
                if p.returncode == 0 or "target wasn't found" in tail:
                    self.debug(f"GHunt found no Google account for {eventData}: {tail}")
                else:
                    self.error(f"GHunt failed on {eventData}: {tail}")
                return
            try:
                data = json.loads(out.read_text(encoding="utf-8"))
            except Exception as e:
                self.error(f"Couldn't parse GHunt's JSON report: {e}")
                return

        if not isinstance(data, dict):
            self.error("GHunt's JSON report was not an object.")
            return

        for evt_type, evt_data in self.parseReport(data):
            self.notifyListeners(SpiderFootEvent(evt_type, evt_data, self.__name__, event))

# End of sfp_tool_ghunt class

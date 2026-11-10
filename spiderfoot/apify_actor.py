"""Run an Apify Actor synchronously for the sfp_apify_* modules."""
from __future__ import annotations

import json
import urllib.parse

# Plain fetch, not SpiderFoot.fetchUrl: the stealth middleware retries "blocked" responses,
# and every retry of a run-sync call is another paid Actor run. Apify is the service, not
# the target, so throttling and UA rotation do nothing useful here.
from spiderfoot.sflib.network import fetchUrl

APIFY_API = "https://api.apify.com/v2"


def run_actor(module, actor: str, run_input: dict) -> list | None:
    """Return the Actor's dataset items (error rows dropped), or None after logging why.

    Uses the module's `api_key`, `max_charge_usd` and `run_timeout` options. Auth and
    credit failures set errorState so the rest of the scan does not repeat them.
    """
    token = module.opts.get("api_key")
    if not token:
        module.error(f"You enabled {module.__class__.__name__} but did not set an Apify API token.")
        module.errorState = True
        return None
    wait = int(min(int(module.opts.get("run_timeout", 290)), 290))  # run-sync caps at 300 s
    query = urllib.parse.urlencode({
        "maxTotalChargeUsd": module.opts.get("max_charge_usd"),
        "timeout": wait,
        "clean": "true",
    })
    res = fetchUrl(
        f"{APIFY_API}/acts/{actor}/run-sync-get-dataset-items?{query}",
        timeout=wait + 15,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        noLog=True,
        postData=json.dumps(run_input),
    ) or {}
    code = str(res.get("code"))
    if code in ("401", "403"):
        module.error("Apify rejected the API token.")
        module.errorState = True
        return None
    if code == "402":
        module.error("Apify spend limit or plan credit exhausted.")
        module.errorState = True
        return None
    if not code.startswith("2"):
        module.error(f"Apify Actor {actor} returned HTTP {code}.")
        return None
    try:
        items = json.loads(res.get("content") or "")
    except ValueError:
        module.error(f"Apify Actor {actor} returned invalid JSON.")
        return None
    if not isinstance(items, list):
        module.error(f"Apify Actor {actor} did not return a list.")
        return None
    return [i for i in items if isinstance(i, dict) and not i.get("error")]

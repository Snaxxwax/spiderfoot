"""A stop requested while waitForThreads waits out a long-running module must be seen.

Regression: the final-pass wait loop polled threadsFinished() but never the scan status,
so an ABORT-REQUESTED scan kept running its slowest module (sfp_accounts, ~8 minutes of
outbound requests) to completion.
"""
import queue
import threading
from types import SimpleNamespace

from spiderfoot.scan.scanner import SpiderFootScanner


class _Module:
    __name__ = "sfp_slow"

    def __init__(self):
        self.incomingEventQueue = queue.Queue()
        self.outgoingEventQueue = queue.Queue()
        self.errorState = False
        self.running = False
        self._stopScanning = False

    def start(self):
        pass


class _Db:
    def __init__(self):
        self.calls = 0

    def scanInstanceGet(self, scan_id):
        self.calls += 1
        # RUNNING while the final pass begins; the stop arrives during the wait.
        status = "RUNNING" if self.calls < 3 else "ABORT-REQUESTED"
        return [scan_id, "n", "t", 0, 0, 0, status]


def test_abort_is_seen_during_the_final_pass_wait():
    scanner = object.__new__(SpiderFootScanner)
    module = _Module()
    scanner.eventQueue = queue.Queue()
    scanner._SpiderFootScanner__dbh = _Db()
    scanner._SpiderFootScanner__scanId = "S1"
    scanner._SpiderFootScanner__moduleInstances = {"sfp_slow": module}
    scanner._SpiderFootScanner__sharedThreadPool = SimpleNamespace(shutdown=lambda wait: None)
    scanner._SpiderFootScanner__sf = SimpleNamespace(debug=lambda *a, **k: None,
                                                     error=lambda *a, **k: None)
    outcome = {}

    def run():
        try:
            scanner.waitForThreads()
            outcome["result"] = "returned"
        except AssertionError as exc:
            outcome["result"] = str(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    # The FINISHED marker the final pass enqueues is never consumed: without the fix this
    # loop spins until the module finishes, i.e. forever here.
    thread.join(10)
    assert outcome.get("result") == "ABORT-REQUESTED"
    assert module._stopScanning is True

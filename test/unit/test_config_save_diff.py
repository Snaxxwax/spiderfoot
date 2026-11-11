"""save_config writes only what this process changed.

Regression: with two API workers, a save on one wrote its whole stale in-memory
config back and emptied an API key saved through the other worker.
"""
from unittest import mock

from spiderfoot.api import dependencies
from spiderfoot.config.app_config import AppConfig


def _config():
    cfg = dependencies.Config(_skip_db=True, _app_config=AppConfig.from_dict({
        "_useragent": "x",
        "__modules__": {
            "sfp_a": {"opts": {"api_key": ""}},
            "sfp_b": {"opts": {"api_key": ""}},
        },
    }))
    cfg._snapshot_saved()
    return cfg


def _set_module_opt(cfg, module, value):
    # Same mutation as PATCH /modules/{name}/options.
    cfg.get_config()["__modules__"][module]["opts"].update({"api_key": value})


def _saves(cfg, *edits):
    with mock.patch.object(dependencies, "SpiderFootDb") as db:
        for edit in edits:
            edit()
            cfg.save_config()
    return [c.args[0] for c in db.return_value.configSet.call_args_list]


def test_save_writes_only_the_changed_option():
    cfg = _config()
    assert _saves(cfg, lambda: _set_module_opt(cfg, "sfp_a", "key-a")) == [{"sfp_a:api_key": "key-a"}]


def test_stale_process_cannot_overwrite_options_it_did_not_change():
    # Worker 2 never saw worker 1 save sfp_a; its own save must not touch sfp_a.
    worker2 = _config()
    assert _saves(worker2, lambda: _set_module_opt(worker2, "sfp_b", "key-b")) == [{"sfp_b:api_key": "key-b"}]


def test_unchanged_save_writes_nothing():
    cfg = _config()
    assert _saves(cfg, lambda: _set_module_opt(cfg, "sfp_a", "key-a"), lambda: None) == [{"sfp_a:api_key": "key-a"}]

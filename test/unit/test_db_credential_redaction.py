"""The PostgreSQL DSN carries the password: it must never reach a log, an exception or a
traceback. Regression: a pool-exhausted / unreachable-database error logged the full DSN."""
import logging
import traceback

import pytest

from spiderfoot.db.db_core import DbCore, redact_credentials

SECRET = "S3cretPw-not-real"


@pytest.mark.parametrize("dsn", [
    f"postgresql://spiderfoot:{SECRET}@127.0.0.1:1/spiderfoot?connect_timeout=1",
    f"host=127.0.0.1 port=1 user=spiderfoot password={SECRET} connect_timeout=1 bogus",
])
def test_database_error_path_never_exposes_the_password(dsn, caplog):
    DbCore._pool = None
    caplog.set_level(logging.DEBUG)
    with pytest.raises(OSError) as info:
        DbCore({"__database": dsn, "__dbtype": "postgresql"})
    DbCore._pool = None
    rendered = "".join(traceback.format_exception(info.value))
    assert SECRET not in caplog.text
    assert SECRET not in str(info.value)
    assert SECRET not in rendered
    assert "Error connecting to PostgreSQL database" in str(info.value)


def test_redact_credentials_forms():
    assert redact_credentials(f"postgresql://u:{SECRET}@db:5432/x") == "postgresql://u:***@db:5432/x"
    assert redact_credentials(f"password={SECRET} host=db") == "password=*** host=db"
    assert redact_credentials(f"password='{SECRET}' host=db") == "password=*** host=db"
    assert redact_credentials("postgresql://db:5432/x") == "postgresql://db:5432/x"

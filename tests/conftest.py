"""Shared fixtures."""

import os

import psycopg
import pytest

from olist_ai_analyst.config import Settings
from olist_ai_analyst.db import run_query


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings for a reachable warehouse; integration tests are skipped without one.

    Set REQUIRE_WAREHOUSE=1 (as the CI does) to fail instead of skipping.
    """
    settings = Settings()
    try:
        run_query(settings, "select 1")
    except psycopg.OperationalError as exc:
        if os.environ.get("REQUIRE_WAREHOUSE") == "1":
            pytest.fail(f"warehouse not reachable: {exc}")
        pytest.skip(f"warehouse not reachable: {exc}")
    return settings

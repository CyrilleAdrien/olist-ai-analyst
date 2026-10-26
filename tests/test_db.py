"""Integration tests: they run against a real warehouse and are skipped when none is reachable."""

import psycopg
import pytest

from olist_ai_analyst.db import run_query


@pytest.mark.integration
def test_agent_reads_the_marts(settings):
    result = run_query(settings, "select count(*) as orders from fct_orders")
    assert result.columns == ["orders"]
    assert result.rows[0][0] > 0


@pytest.mark.integration
def test_agent_cannot_write(settings):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        run_query(settings, "create table marts.agent_was_here (id int)")


@pytest.mark.integration
def test_agent_cannot_read_raw_data(settings):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_query(settings, "select * from raw.orders limit 1")

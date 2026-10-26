import datetime as dt
from decimal import Decimal

import psycopg
import pytest
from langchain_core.language_models import FakeListChatModel

from olist_ai_analyst.agent import build_agent
from olist_ai_analyst.config import Settings
from olist_ai_analyst.db import QueryResult, run_query
from olist_ai_analyst.evaluation import load_cases, results_match, run_case, summarize
from olist_ai_analyst.examples import EXAMPLES
from olist_ai_analyst.schema_context import build_schema_context
from olist_ai_analyst.sql_guard import validate_sql

REFERENCE = QueryResult(["state", "late_pct"], [("AL", Decimal("21.41")), ("MA", Decimal("17.36"))])


def test_same_values_in_another_order_and_names_match():
    actual = QueryResult(["rate", "uf"], [(21.4109, "AL"), (17.36, "MA")][::-1])
    assert results_match(REFERENCE, actual) == (True, "")


def test_extra_columns_are_allowed():
    actual = QueryResult(["uf", "orders", "rate"], [("AL", 400, 21.41), ("MA", 700, 17.36)])
    assert results_match(REFERENCE, actual)[0]


def test_wrong_values_or_row_count_fail():
    wrong = QueryResult(["uf", "rate"], [("AL", 0.2141), ("MA", 0.1736)])
    assert results_match(REFERENCE, wrong) == (
        False,
        "no column matches the reference column late_pct",
    )
    assert (
        results_match(REFERENCE, QueryResult(["uf", "r"], [("AL", 21.41)]))[1]
        == "1 rows instead of 2"
    )


def test_midnight_timestamps_match_dates():
    expected = QueryResult(["month"], [(dt.date(2017, 1, 1),)])
    assert results_match(expected, QueryResult(["m"], [(dt.datetime(2017, 1, 1),)]))[0]


def test_cases_are_unique_and_differ_from_the_examples():
    cases = load_cases()
    assert len(cases) == 30
    assert len({c.id for c in cases}) == 30
    assert not {c.question for c in cases} & {e.question for e in EXAMPLES}
    assert all(c.sql or c.expect == "out_of_scope" for c in cases)


@pytest.fixture(scope="module")
def settings() -> Settings:
    settings = Settings()
    try:
        run_query(settings, "select 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"warehouse not reachable: {exc}")
    return settings


@pytest.mark.integration
def test_reference_queries_pass_the_guard_and_run(settings):
    tables = {t.name: {c.name for c in t.columns} for t in build_schema_context(settings).tables}
    for case in load_cases():
        if case.sql:
            run_query(settings, validate_sql(case.sql, tables))


@pytest.mark.integration
def test_an_agent_that_writes_the_reference_sql_gets_full_marks(settings):
    context = build_schema_context(settings)
    outcomes = []
    for case in load_cases():
        reply = f"```sql\n{case.sql}\n```" if case.sql else "OUT_OF_SCOPE"
        model = FakeListChatModel(responses=[reply, "Réponse."])
        agent = build_agent(model, context, lambda sql: run_query(settings, sql))
        outcomes.append(run_case(case, agent, lambda sql: run_query(settings, sql)))
    failed = [(o.id, o.reason) for o in outcomes if not o.passed]
    assert failed == []
    assert summarize(outcomes)["accuracy"] == 100.0

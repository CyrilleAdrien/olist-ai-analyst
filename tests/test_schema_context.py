from pathlib import Path

import psycopg
import pytest

from olist_ai_analyst.config import Settings
from olist_ai_analyst.db import run_query
from olist_ai_analyst.examples import EXAMPLES
from olist_ai_analyst.schema_context import build_schema_context, load_dbt_docs, merge

# A subset of the manifest written by dbt build in Olist-Analytics
MANIFEST = Path(__file__).parent / "fixtures" / "manifest.json"

DB_TABLES = {
    "fct_orders": [("order_id", "text"), ("is_late", "boolean"), ("new_column", "integer")],
    "dim_dates": [("date_day", "date")],
}


def test_only_models_of_the_schema_are_read():
    docs = load_dbt_docs(MANIFEST, "marts")
    assert set(docs.tables) == {"fct_orders", "dim_dates"}
    assert docs.tables["fct_orders"].startswith("One row per order")


def test_kpi_definitions_are_written_once_and_referenced_by_tag():
    docs = load_dbt_docs(MANIFEST, "marts")
    assert docs.kpis["late_rate"].startswith("Late delivery rate: delivered orders")
    assert docs.columns["fct_orders"]["is_late"] == "[late_rate]"
    assert docs.columns["fct_orders"]["order_id"] == "Primary key. [orders]"


def test_warehouse_decides_which_tables_and_columns_exist():
    context = merge("marts", DB_TABLES, load_dbt_docs(MANIFEST, "marts"), [])
    assert [t.name for t in context.tables] == ["dim_dates", "fct_orders"]
    columns = {c.name: c for c in context.tables[1].columns}
    assert list(columns) == ["order_id", "is_late", "new_column"]
    assert columns["new_column"].description == ""
    assert columns["is_late"].data_type == "boolean"


def test_prompt_lists_tables_kpis_and_examples():
    context = merge("marts", DB_TABLES, load_dbt_docs(MANIFEST, "marts"), EXAMPLES[:1])
    prompt = context.to_prompt()
    assert "Table fct_orders: One row per order" in prompt
    assert "  - is_late (boolean): [late_rate]" in prompt
    assert "  - new_column (integer)\n" in prompt
    assert "  - [late_rate] Late delivery rate:" in prompt
    assert f"SQL: {EXAMPLES[0].sql}" in prompt


def test_context_works_without_manifest():
    from olist_ai_analyst.schema_context import DbtDocs

    prompt = merge("marts", DB_TABLES, DbtDocs(), []).to_prompt()
    assert "Table dim_dates\n" in prompt
    assert "KPI definitions" not in prompt


@pytest.fixture(scope="module")
def settings() -> Settings:
    settings = Settings()
    try:
        run_query(settings, "select 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"warehouse not reachable: {exc}")
    return settings


@pytest.mark.integration
def test_context_covers_every_mart(settings):
    context = build_schema_context(settings)
    names = {t.name for t in context.tables}
    assert {"fct_orders", "fct_order_items", "dim_customers", "dim_products"} <= names


@pytest.mark.integration
@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.question)
def test_examples_pass_the_guard_and_run(settings, example):
    from olist_ai_analyst.sql_guard import validate_sql

    tables = {t.name: {c.name for c in t.columns} for t in build_schema_context(settings).tables}
    result = run_query(settings, validate_sql(example.sql, tables))
    assert result.rows


@pytest.mark.integration
def test_agent_runs_a_real_query_end_to_end(settings):
    from langchain_core.language_models import FakeListChatModel

    from olist_ai_analyst.agent import ask, build_agent

    reply = f"```sql\n{EXAMPLES[0].sql}\n```"
    agent = build_agent(
        FakeListChatModel(responses=[reply]),
        build_schema_context(settings),
        lambda sql: run_query(settings, sql),
    )
    result = ask("Quel est le chiffre d'affaires total ?", agent)
    assert result.status == "ok"
    assert result.columns == ["revenue_brl", "average_basket_brl"]

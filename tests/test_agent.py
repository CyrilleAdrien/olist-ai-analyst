import psycopg
from langchain_core.language_models import FakeListChatModel

from olist_ai_analyst.agent import ask, build_agent
from olist_ai_analyst.db import QueryResult
from olist_ai_analyst.schema_context import Column, SchemaContext, Table

CONTEXT = SchemaContext(
    schema="marts",
    tables=[Table("fct_orders", [Column("order_id", "text"), Column("is_late", "boolean")])],
    kpis={},
    examples=[],
)


class FakeWarehouse:
    """Answers queries from a list of results or errors, and records what it ran."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.queries: list[str] = []

    def __call__(self, sql: str) -> QueryResult:
        self.queries.append(sql)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def run(replies, warehouse, question="Combien de commandes ?"):
    agent = build_agent(FakeListChatModel(responses=replies), CONTEXT, warehouse)
    return ask(question, agent)


def test_first_query_succeeds():
    warehouse = FakeWarehouse(QueryResult(["orders"], [(42,)]))
    result = run(["```sql\nselect count(*) as orders from fct_orders\n```"], warehouse)
    assert result.status == "ok"
    assert result.rows == [(42,)]
    assert result.attempts == 1
    assert warehouse.queries == ["SELECT COUNT(*) AS orders FROM fct_orders LIMIT 1000"]


def test_database_error_is_sent_back_and_fixed():
    warehouse = FakeWarehouse(
        psycopg.errors.UndefinedColumn('column "nb" does not exist'),
        QueryResult(["orders"], [(42,)]),
    )
    result = run(
        ["select nb from fct_orders", "select count(*) as orders from fct_orders"], warehouse
    )
    assert result.status == "ok"
    assert result.attempts == 2


def test_unsafe_query_never_reaches_the_warehouse():
    warehouse = FakeWarehouse(QueryResult(["orders"], [(42,)]))
    result = run(["drop table fct_orders", "select count(*) as orders from fct_orders"], warehouse)
    assert result.status == "ok"
    assert len(warehouse.queries) == 1


def test_agent_gives_up_after_three_attempts():
    warehouse = FakeWarehouse()
    result = run(["select * from users"] * 3, warehouse)
    assert result.status == "failed"
    assert result.attempts == 3
    assert "Unknown table users" in result.error
    assert warehouse.queries == []


def test_empty_result_triggers_one_more_try():
    warehouse = FakeWarehouse(QueryResult(["n"], []), QueryResult(["n"], [(3,)]))
    replies = ["select 1 as n from fct_orders where false", "select 3 as n from fct_orders"]
    result = run(replies, warehouse)
    assert result.status == "ok"
    assert result.rows == [(3,)]


def test_out_of_scope_question_stops_without_query():
    warehouse = FakeWarehouse()
    result = run(["OUT_OF_SCOPE"], warehouse, question="Quel temps fait-il à Paris ?")
    assert result.status == "out_of_scope"
    assert warehouse.queries == []

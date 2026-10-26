"""The SQL agent: a LangGraph loop that writes a query, checks it, runs it and fixes it.

generate_sql -> run_sql -> done
     ^             |
     +-- error ----+   (at most max_attempts queries)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

import psycopg
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from olist_ai_analyst.config import Settings
from olist_ai_analyst.db import QueryResult, run_query
from olist_ai_analyst.llm import get_chat_model
from olist_ai_analyst.schema_context import SchemaContext, build_schema_context
from olist_ai_analyst.sql_guard import UnsafeQueryError, extract_sql, validate_sql

OUT_OF_SCOPE = "OUT_OF_SCOPE"
Status = Literal["running", "ok", "out_of_scope", "failed"]

SYSTEM_PROMPT = """You are a data analyst for Olist, a Brazilian e-commerce marketplace.
You answer business questions, asked in French, by writing one PostgreSQL query.

Rules:
- Use only the tables and columns listed below. Never invent a column.
- Revenue, order and review KPIs only count delivered orders (is_delivered), as defined below.
- Amounts are in BRL. Category names are in product_category_name_english.
- Joins: customer location (state, city) is in dim_customers, joined on customer_unique_id;
  seller location is in dim_sellers, joined to fct_order_items on seller_id; products are
  joined to fct_order_items on product_id; dim_dates only holds calendar columns, joined on
  order_date = date_day.
- Give readable column aliases in English (snake_case) and round averages and rates to 2 decimals.
- Reply with the query only, in a ```sql block, without explanation.
- If the question cannot be answered with these tables (weather, code, opinions, other
  companies...), reply with the single word {out_of_scope}.

{schema}
"""


class AgentState(TypedDict):
    question: str
    sql: str
    history: list[str]
    columns: list[str]
    rows: list[tuple[Any, ...]]
    error: str
    attempts: int
    status: Status


@dataclass
class AgentResult:
    question: str
    status: Status
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    error: str = ""
    attempts: int = 0


def _attempt(sql: str, error: str) -> str:
    return f"This query failed:\n```sql\n{sql}\n```\nError: {error}"


def build_agent(
    llm: BaseChatModel,
    context: SchemaContext,
    run_sql: Callable[[str], QueryResult],
    max_attempts: int = 3,
):
    system = SystemMessage(
        SYSTEM_PROMPT.format(out_of_scope=OUT_OF_SCOPE, schema=context.to_prompt())
    )
    tables = {table.name: {col.name for col in table.columns} for table in context.tables}

    def generate_sql(state: AgentState) -> dict:
        prompt = f"Question: {state['question']}"
        if state["history"]:
            # Every failed attempt is shown, so that the model does not repeat a mistake
            prompt += "\n\n" + "\n\n".join(state["history"])
            prompt += "\n\nWrite a corrected query that fixes these errors."
        reply = str(llm.invoke([system, HumanMessage(prompt)]).content)
        if reply.strip().strip(".").upper() == OUT_OF_SCOPE:
            return {"status": "out_of_scope", "sql": ""}
        return {"sql": extract_sql(reply), "attempts": state["attempts"] + 1}

    def execute(state: AgentState) -> dict:
        try:
            sql = validate_sql(state["sql"], tables, context.schema)
            result = run_sql(sql)
        except (UnsafeQueryError, psycopg.Error) as exc:
            error = str(exc).strip()
            failed = state["attempts"] >= max_attempts
            return {
                "error": error,
                "history": [*state["history"], _attempt(state["sql"], error)],
                "status": "failed" if failed else "running",
            }
        if not result.rows and state["attempts"] < max_attempts:
            error = "The query returned no rows. Check the filters and the values used."
            return {
                "sql": sql,
                "error": error,
                "history": [*state["history"], _attempt(sql, error)],
            }
        return {
            "sql": sql,
            "columns": result.columns,
            "rows": result.rows,
            "error": "",
            "status": "ok",
        }

    def after_generate(state: AgentState) -> str:
        return END if state["status"] == "out_of_scope" else "execute"

    def after_execute(state: AgentState) -> str:
        return "generate_sql" if state["status"] == "running" else END

    graph = StateGraph(AgentState)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute", execute)
    graph.add_edge(START, "generate_sql")
    graph.add_conditional_edges("generate_sql", after_generate, ["execute", END])
    graph.add_conditional_edges("execute", after_execute, ["generate_sql", END])
    return graph.compile()


def ask(question: str, agent) -> AgentResult:
    state = agent.invoke(
        {
            "question": question,
            "sql": "",
            "history": [],
            "columns": [],
            "rows": [],
            "error": "",
            "attempts": 0,
            "status": "running",
        }
    )
    return AgentResult(
        question=question,
        status=state["status"],
        sql=state["sql"],
        columns=state["columns"],
        rows=state["rows"],
        error=state["error"],
        attempts=state["attempts"],
    )


def build_default_agent(settings: Settings):
    return build_agent(
        get_chat_model(settings),
        build_schema_context(settings),
        lambda sql: run_query(settings, sql),
    )

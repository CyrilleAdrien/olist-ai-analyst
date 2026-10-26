# Olist AI Analyst

An AI agent that answers business questions in French on the Olist data warehouse: it writes
the SQL, runs it read-only, checks the result and replies with a chart.

It builds on [Olist-Analytics](https://github.com/CyrilleAdrien/Olist-Analytics), which loads
the Olist dataset into PostgreSQL and models it with dbt. The agent only reads the `marts`
schema, through a dedicated read-only role.

## Stack

| Layer | Choice |
| --- | --- |
| LLM | Ollama, `qwen2.5-coder:7b` by default (free, runs locally); Groq, Claude or OpenAI via `LLM_PROVIDER` |
| Agent | LangGraph, sqlglot to check the SQL before it runs |
| Warehouse | PostgreSQL 16 from Olist-Analytics, read-only role on `marts` |
| Tooling | uv, ruff, pytest |

## Getting started

Requirements: the Olist-Analytics warehouse running (`make all` in that repository),
[uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com).

```bash
ollama pull qwen2.5-coder:7b
make install   # creates .env from .env.example, then installs the dependencies
```

Edit `.env`: copy `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` from the `.env` of
Olist-Analytics and choose a password for `AGENT_DB_PASSWORD`. Then:

```bash
make role      # creates the read-only role olist_agent (safe to run again)
make doctor    # checks the warehouse connection and the model
make schema    # prints the schema context sent to the model
make ask Q="Quel est le panier moyen ?"
make test      # unit tests, plus integration tests when the warehouse is reachable
```

`make doctor` prints one line per check, for example:

```
[ok] warehouse: 6 tables in marts: dim_customers, dim_dates, dim_products, dim_sellers, fct_order_items, fct_orders
[ok] model: ollama/qwen2.5-coder:7b replied: OK
```

## Schema context

The LLM only knows the warehouse through the context built by `schema_context.py`:

- the tables and columns the read-only role can see, read from `information_schema`;
- their descriptions and the KPI definitions, read from the dbt `manifest.json` of
  Olist-Analytics (`DBT_MANIFEST_PATH`, written by `make build` there). Each KPI definition is
  written once and columns refer to it with a tag such as `[late_rate]`;
- a few question/SQL examples in French (`examples.py`).

`make schema` prints this context (about 2,000 tokens). Ollama gets an 8,192-token window
(`OLLAMA_NUM_CTX`), since its default would cut the prompt.

## How the agent works

`agent.py` is a LangGraph loop of two nodes:

1. `generate_sql`: the model gets the schema context and the question, and replies with one
   query, or `OUT_OF_SCOPE` when the data cannot answer it.
2. `execute`: `sql_guard.py` checks the query with sqlglot (one `SELECT`, only tables of
   `marts`, at most 1,000 rows), then the read-only role runs it.

When the query is refused, fails or returns no rows, the error goes back to the model, which
writes a corrected query. The agent stops after 3 queries.

```bash
make ask Q="Quels États ont le plus de retards de livraison ?"
```

## Safety

The agent connects with the `olist_agent` role, which can only `SELECT` from `marts`. Each
session is also opened read-only, with a 10 second statement timeout.

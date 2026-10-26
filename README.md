# Olist AI Analyst

[![CI](https://github.com/CyrilleAdrien/olist-ai-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/CyrilleAdrien/olist-ai-analyst/actions/workflows/ci.yml)

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
| Charts | Plotly |
| Interface | Streamlit |
| Warehouse | PostgreSQL 16 from Olist-Analytics, read-only role on `marts` |
| Tooling | uv, ruff, pytest, GitHub Actions |

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
make eval      # runs the 30 evaluation questions and writes a report
make app       # opens the chat interface on http://localhost:8501
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

`agent.py` is a LangGraph graph of three nodes:

1. `generate_sql`: the model gets the schema context and the question, and replies with one
   query, or `OUT_OF_SCOPE` when the data cannot answer it.
2. `execute`: `sql_guard.py` checks the query with sqlglot (one `SELECT`, only tables of
   `marts`, at most 1,000 rows), then the read-only role runs it.

3. `write_answer`: the model writes a short answer in French from the result (`answer.py`).
   Small models compute badly in their head, so the figures it may quote (total, average,
   highest, lowest) are computed in Python and the table is formatted the French way, with
   the state names. Every number of the answer is checked against them: an answer with a
   number from nowhere is rewritten once, then replaced by a plain summary of the figures.

When the query is refused, fails or returns no rows, the error goes back to the model, which
writes a corrected query, with every failed attempt in view. The agent stops after 3 queries.

`chart.py` then picks a chart from the shape of the result, without the model: a line when the
first column is a date, horizontal bars (top 20) when it is a label, no chart for a single
value. `make ask` saves it to `chart.html`.

```bash
make ask Q="Quels États ont le plus de retards de livraison ?"
```

## Chat interface

```bash
make app       # http://localhost:8501
```

`app.py` is a Streamlit chat: type a question in French or click an example. Each answer shows
the text, the chart, the SQL with the number of queries and the time taken, and the data
table. The conversation stays on screen until you clear it.

## Evaluation

`evals/cases.toml` holds 30 questions in French: 8 KPIs (including the reference figures of
Olist-Analytics), 6 trends over time, 8 rankings and filters, 4 rates and 4 questions the agent
must decline (weather, poem, a request to delete data, a prompt injection). Each answerable
question comes with the SQL that gives the right result.

A case passes when the agent's result holds the same values as the reference result: column
names, row order and extra columns are ignored, numbers are compared to 2 decimals. So the
score measures the answer, not the way the SQL is written.

```bash
make eval                           # the model of .env
make eval MODEL=qwen2.5-coder:14b   # another model, after ollama pull
```

Each run writes `evals/results/<provider>-<model>.md` (summary by category, every case) and a
`.json` file with the SQL and the answer of every question.

## Continuous integration

GitHub Actions runs two jobs on every pull request and on `main`:

- **Lint and unit tests**: `ruff check`, `ruff format --check` and the unit tests. They use fake
  chat models, so no LLM and no API key are needed.
- **Integration tests**: starts PostgreSQL 16, checks out Olist-Analytics, loads its CI sample
  and runs `dbt build`, creates the read-only role, then runs the tests marked `integration`
  against the real marts. `REQUIRE_WAREHOUSE=1` makes them fail instead of being skipped.

The evaluation is not part of CI: it needs a real model (`make eval` on your machine).

## Safety

The agent connects with the `olist_agent` role, which can only `SELECT` from `marts`. Each
session is also opened read-only, with a 10 second statement timeout.

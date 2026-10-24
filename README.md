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
| Agent | LangChain chat models, LangGraph (next steps) |
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
make test      # unit tests, plus integration tests when the warehouse is reachable
```

`make doctor` prints one line per check, for example:

```
[ok] warehouse: 6 tables in marts: dim_customers, dim_dates, dim_products, dim_sellers, fct_order_items, fct_orders
[ok] model: ollama/qwen2.5-coder:7b replied: OK
```

## Safety

The agent connects with the `olist_agent` role, which can only `SELECT` from `marts`. Each
session is also opened read-only, with a 10 second statement timeout.

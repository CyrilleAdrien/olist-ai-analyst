"""Command line entry point: `olist-ai-analyst doctor` checks the warehouse and the model."""

import argparse
import sys

import httpx

from olist_ai_analyst.config import get_settings
from olist_ai_analyst.db import run_query
from olist_ai_analyst.llm import get_chat_model


def check_warehouse() -> str:
    settings = get_settings()
    tables = run_query(
        settings,
        "select table_name from information_schema.tables"
        " where table_schema = %(schema)s order by table_name",
        {"schema": settings.agent_db_schema},
    )
    names = [row[0] for row in tables.rows]
    if not names:
        raise RuntimeError(f"No table visible in schema {settings.agent_db_schema}")
    return f"{len(names)} tables in {settings.agent_db_schema}: {', '.join(names)}"


def check_model() -> str:
    settings = get_settings()
    try:
        reply = get_chat_model(settings).invoke("Réponds uniquement par le mot OK.")
    except (ConnectionError, httpx.ConnectError) as exc:
        if settings.llm_provider == "ollama":
            raise ConnectionError(
                f"Ollama is not reachable at {settings.ollama_base_url}, open the Ollama app"
            ) from exc
        raise
    return f"{settings.llm_provider}/{settings.model_name} replied: {str(reply.content).strip()}"


def doctor() -> int:
    failed = False
    for name, check in (("warehouse", check_warehouse), ("model", check_model)):
        try:
            print(f"[ok] {name}: {check()}")
        except Exception as exc:  # report every failure, then exit non-zero
            failed = True
            print(f"[fail] {name}: {exc}")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="olist-ai-analyst")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check the warehouse connection and the LLM")
    args = parser.parse_args()
    if args.command == "doctor":
        sys.exit(doctor())


if __name__ == "__main__":
    main()

"""Command line entry point: `olist-ai-analyst doctor` checks the warehouse and the model."""

import argparse
import sys

import httpx

from olist_ai_analyst.agent import ask, build_default_agent
from olist_ai_analyst.config import get_settings
from olist_ai_analyst.db import run_query
from olist_ai_analyst.llm import get_chat_model
from olist_ai_analyst.schema_context import build_schema_context


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


def show_schema() -> int:
    """Print the schema context sent to the LLM, with a rough size in tokens."""
    prompt = build_schema_context(get_settings()).to_prompt()
    print(prompt)
    print(f"\n~{len(prompt) // 4} tokens", file=sys.stderr)
    return 0


def ask_question(question: str) -> int:
    """Run the agent on one question and print the SQL and the first rows."""
    result = ask(question, build_default_agent(get_settings()))
    if result.status == "out_of_scope":
        print("Question hors du périmètre des données Olist.")
        return 0
    print(f"SQL ({result.attempts} attempt(s)):\n{result.sql}\n")
    if result.status == "failed":
        print(f"Failed: {result.error}")
        return 1
    print(" | ".join(result.columns))
    for row in result.rows[:20]:
        print(" | ".join(str(value) for value in row))
    if len(result.rows) > 20:
        print(f"... {len(result.rows)} rows")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="olist-ai-analyst")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check the warehouse connection and the LLM")
    sub.add_parser("schema", help="Print the schema context sent to the LLM")
    ask_parser = sub.add_parser("ask", help="Ask a question in French")
    ask_parser.add_argument("question")
    args = parser.parse_args()
    if args.command == "ask":
        sys.exit(ask_question(args.question))
    commands = {"doctor": doctor, "schema": show_schema}
    sys.exit(commands[args.command]())


if __name__ == "__main__":
    main()

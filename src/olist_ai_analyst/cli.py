"""Command line entry point: `olist-ai-analyst doctor` checks the warehouse and the model."""

import argparse
import sys

import httpx

from olist_ai_analyst.agent import ask, build_default_agent
from olist_ai_analyst.chart import make_chart
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


def ask_question(question: str, chart_path: str | None = None) -> int:
    """Run the agent on one question: print the answer, the SQL and the first rows."""
    result = ask(question, build_default_agent(get_settings()))
    print(f"{result.answer}\n")
    if result.status == "out_of_scope":
        return 0
    print(f"SQL ({result.attempts} attempt(s)):\n{result.sql}\n")
    if result.status == "failed":
        print(f"Last error: {result.error}")
        return 1
    print(" | ".join(result.columns))
    for row in result.rows[:20]:
        print(" | ".join(str(value) for value in row))
    if len(result.rows) > 20:
        print(f"... {len(result.rows)} rows")
    figure = make_chart(result.columns, result.rows)
    if chart_path and figure is not None:
        figure.write_html(chart_path, include_plotlyjs="cdn")
        print(f"\nChart saved to {chart_path}")
    return 0


def evaluate(model: str | None, limit: int | None) -> int:
    """Run the evaluation set and write the report in evals/results/."""
    from olist_ai_analyst.agent import build_agent
    from olist_ai_analyst.evaluation import load_cases, run_case, write_report
    from olist_ai_analyst.schema_context import build_schema_context

    settings = get_settings()
    if model:
        settings = settings.model_copy(update={"llm_model": model})
    agent = build_agent(
        get_chat_model(settings),
        build_schema_context(settings),
        lambda sql: run_query(settings, sql),
    )
    cases = load_cases()[:limit]
    outcomes = []
    for i, case in enumerate(cases, 1):
        outcome = run_case(case, agent, lambda sql: run_query(settings, sql))
        mark = "pass" if outcome.passed else f"FAIL ({outcome.reason})"
        print(f"[{i}/{len(cases)}] {case.id}: {mark} in {outcome.seconds} s")
        outcomes.append(outcome)
    report = write_report(f"{settings.llm_provider}/{settings.model_name}", outcomes)
    print(f"\n{sum(o.passed for o in outcomes)}/{len(outcomes)} passed, report: {report}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="olist-ai-analyst")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check the warehouse connection and the LLM")
    sub.add_parser("schema", help="Print the schema context sent to the LLM")
    ask_parser = sub.add_parser("ask", help="Ask a question in French")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--chart", metavar="PATH", help="Save the chart as an HTML file")
    eval_parser = sub.add_parser("eval", help="Run the evaluation set")
    eval_parser.add_argument("--model", help="Model to evaluate instead of LLM_MODEL")
    eval_parser.add_argument("--limit", type=int, help="Only the first N cases")
    args = parser.parse_args()
    if args.command == "eval":
        sys.exit(evaluate(args.model, args.limit))
    if args.command == "ask":
        sys.exit(ask_question(args.question, args.chart))
    commands = {"doctor": doctor, "schema": show_schema}
    sys.exit(commands[args.command]())


if __name__ == "__main__":
    main()

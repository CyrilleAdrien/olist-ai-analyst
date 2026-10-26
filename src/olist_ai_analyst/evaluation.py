"""Evaluate the agent on evals/cases.toml: execution accuracy, scope handling and latency.

A case passes when the agent's result holds the same values as the reference result. Column
names and row order are ignored, extra columns are allowed, numbers are compared to 2
decimals: what counts is the answer, not how the SQL is written.
"""

import datetime as dt
import json
import time
import tomllib
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from olist_ai_analyst.agent import ask
from olist_ai_analyst.db import QueryResult

CASES_PATH = Path("evals/cases.toml")
RESULTS_DIR = Path("evals/results")
TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    question: str
    sql: str = ""
    expect: str = "result"


@dataclass
class Outcome:
    id: str
    category: str
    question: str
    passed: bool
    status: str
    attempts: int
    seconds: float
    sql: str
    answer: str
    reason: str


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    return [Case(**case) for case in tomllib.loads(path.read_text())["cases"]]


def _normalize(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    if isinstance(value, dt.datetime) and value.time() == dt.time():
        return value.date()
    return value


def _sort_key(value: Any) -> tuple[str, Any]:
    return (type(value).__name__, "" if value is None else value)


def _same_column(expected: list[Any], actual: list[Any]) -> bool:
    for a, b in zip(sorted(expected, key=_sort_key), sorted(actual, key=_sort_key), strict=True):
        if isinstance(a, Decimal) and isinstance(b, Decimal):
            if abs(a - b) > TOLERANCE:
                return False
        elif a != b:
            return False
    return True


def results_match(expected: QueryResult, actual: QueryResult) -> tuple[bool, str]:
    """Every reference column must match one column of the agent's result, value for value."""
    if len(expected.rows) != len(actual.rows):
        return False, f"{len(actual.rows)} rows instead of {len(expected.rows)}"
    actual_columns = [
        [_normalize(row[i]) for row in actual.rows] for i in range(len(actual.columns))
    ]
    for i, name in enumerate(expected.columns):
        column = [_normalize(row[i]) for row in expected.rows]
        if not any(_same_column(column, other) for other in actual_columns):
            return False, f"no column matches the reference column {name}"
    return True, ""


def run_case(case: Case, agent, run_sql) -> Outcome:
    start = time.perf_counter()
    result = ask(case.question, agent)
    seconds = round(time.perf_counter() - start, 1)
    if case.expect == "out_of_scope":
        passed = result.status != "ok"
        reason = "" if passed else "answered a question it should decline"
    elif result.status != "ok":
        passed, reason = False, f"status {result.status}: {result.error}"
    else:
        passed, reason = results_match(run_sql(case.sql), QueryResult(result.columns, result.rows))
    return Outcome(
        id=case.id,
        category=case.category,
        question=case.question,
        passed=passed,
        status=result.status,
        attempts=result.attempts,
        seconds=seconds,
        sql=result.sql,
        answer=result.answer,
        reason=reason,
    )


def summarize(outcomes: list[Outcome]) -> dict[str, Any]:
    by_category: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        by_category.setdefault(outcome.category, []).append(outcome)
    seconds = sorted(o.seconds for o in outcomes)
    return {
        "passed": sum(o.passed for o in outcomes),
        "total": len(outcomes),
        "accuracy": round(100 * sum(o.passed for o in outcomes) / len(outcomes), 1),
        "by_category": {
            name: f"{sum(o.passed for o in group)}/{len(group)}"
            for name, group in by_category.items()
        },
        "first_try": sum(o.passed and o.attempts == 1 for o in outcomes),
        "median_seconds": seconds[len(seconds) // 2],
        "max_seconds": seconds[-1],
    }


def write_report(model: str, outcomes: list[Outcome], out_dir: Path = RESULTS_DIR) -> Path:
    """Write <model>.json (every detail) and <model>.md (readable report), return the .md."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(outcomes)
    slug = model.replace("/", "-").replace(":", "-")
    run = {"model": model, "date": dt.date.today().isoformat(), "summary": summary}
    (out_dir / f"{slug}.json").write_text(
        json.dumps({**run, "cases": [asdict(o) for o in outcomes]}, indent=2, ensure_ascii=False)
    )
    lines = [
        f"# Evaluation: {model}",
        "",
        f"Run on {run['date']}: **{summary['passed']}/{summary['total']} passed "
        f"({summary['accuracy']} %)**, {summary['first_try']} on the first query, "
        f"median {summary['median_seconds']} s per question (max {summary['max_seconds']} s).",
        "",
        "| Category | Passed |",
        "| --- | --- |",
        *[f"| {name} | {score} |" for name, score in summary["by_category"].items()],
        "",
        "| Case | Result | Queries | Seconds | Reason |",
        "| --- | --- | --- | --- | --- |",
        *[
            f"| {o.id} | {'pass' if o.passed else 'FAIL'} | {o.attempts} | {o.seconds} "
            f"| {o.reason.replace('|', '/').splitlines()[0] if o.reason else ''} |"
            for o in outcomes
        ],
    ]
    report = out_dir / f"{slug}.md"
    report.write_text("\n".join(lines) + "\n")
    return report

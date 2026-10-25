"""Describe the marts schema to the LLM: tables and columns from the warehouse, descriptions and
KPI definitions from the dbt manifest of Olist-Analytics, plus a few question/SQL examples."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from olist_ai_analyst.config import Settings
from olist_ai_analyst.db import run_query
from olist_ai_analyst.examples import EXAMPLES, Example

DOC_CALL = re.compile(r"\{\{\s*doc\(\s*['\"](\w+)['\"]\s*\)\s*\}\}")


@dataclass
class Column:
    name: str
    data_type: str
    description: str = ""


@dataclass
class Table:
    name: str
    columns: list[Column]
    description: str = ""


@dataclass
class DbtDocs:
    """Descriptions read from manifest.json, keyed by table then column name."""

    tables: dict[str, str] = field(default_factory=dict)
    columns: dict[str, dict[str, str]] = field(default_factory=dict)
    kpis: dict[str, str] = field(default_factory=dict)


@dataclass
class SchemaContext:
    schema: str
    tables: list[Table]
    kpis: dict[str, str]
    examples: list[Example]

    def to_prompt(self) -> str:
        lines = [f"PostgreSQL schema `{self.schema}` (read-only). Tables and columns:"]
        for table in self.tables:
            lines.append("")
            lines.append(f"Table {table.name}: {table.description}".rstrip(": "))
            for col in table.columns:
                desc = f": {col.description}" if col.description else ""
                lines.append(f"  - {col.name} ({col.data_type}){desc}")
        if self.kpis:
            lines += ["", "KPI definitions (use them exactly):"]
            lines += [f"  - [{name}] {text}" for name, text in self.kpis.items()]
        if self.examples:
            lines += ["", "Examples:"]
            for example in self.examples:
                lines += ["", f"Question: {example.question}", f"SQL: {example.sql}"]
        return "\n".join(lines)


def _clean(text: str) -> str:
    """Drop the markdown emphasis and collapse whitespace."""
    return " ".join(text.replace("**", "").replace("`", "").split())


def load_dbt_docs(manifest_path: Path, schema: str) -> DbtDocs:
    manifest = json.loads(manifest_path.read_text())
    kpis = {
        doc["name"].removeprefix("kpi_"): _clean(doc["block_contents"])
        for doc in manifest.get("docs", {}).values()
        if doc["name"].startswith("kpi_")
    }

    def describe(text: str) -> str:
        # The manifest may hold rendered doc blocks or raw doc() calls: both become [kpi] tags,
        # so each KPI definition is written once in the prompt.
        text = DOC_CALL.sub(lambda m: f"[{m.group(1).removeprefix('kpi_')}]", text)
        text = _clean(text)
        for name, body in kpis.items():
            text = text.replace(body, f"[{name}]")
        return text

    docs = DbtDocs(kpis=kpis)
    for node in manifest.get("nodes", {}).values():
        if node.get("resource_type") != "model" or node.get("schema") != schema:
            continue
        docs.tables[node["name"]] = describe(node.get("description", ""))
        docs.columns[node["name"]] = {
            name: describe(col.get("description", ""))
            for name, col in node.get("columns", {}).items()
        }
    return docs


def load_db_tables(settings: Settings) -> dict[str, list[tuple[str, str]]]:
    """Tables and columns the agent can actually read, in column order."""
    result = run_query(
        settings,
        "select table_name, column_name, data_type from information_schema.columns"
        " where table_schema = %(schema)s order by table_name, ordinal_position",
        {"schema": settings.agent_db_schema},
    )
    tables: dict[str, list[tuple[str, str]]] = {}
    for table, column, data_type in result.rows:
        tables.setdefault(table, []).append((column, data_type))
    return tables


def merge(
    schema: str,
    db_tables: dict[str, list[tuple[str, str]]],
    docs: DbtDocs,
    examples: list[Example],
) -> SchemaContext:
    """The warehouse decides what exists; dbt only adds the descriptions."""
    tables = [
        Table(
            name=name,
            description=docs.tables.get(name, ""),
            columns=[
                Column(
                    col,
                    data_type.replace(" without time zone", ""),
                    docs.columns.get(name, {}).get(col, ""),
                )
                for col, data_type in columns
            ],
        )
        for name, columns in sorted(db_tables.items())
    ]
    return SchemaContext(schema=schema, tables=tables, kpis=docs.kpis, examples=examples)


def build_schema_context(settings: Settings) -> SchemaContext:
    manifest = Path(settings.dbt_manifest_path).expanduser()
    docs = load_dbt_docs(manifest, settings.agent_db_schema) if manifest.is_file() else DbtDocs()
    return merge(settings.agent_db_schema, load_db_tables(settings), docs, EXAMPLES)

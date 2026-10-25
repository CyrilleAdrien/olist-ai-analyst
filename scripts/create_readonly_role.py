"""Create (or update) the read-only role used by the agent.

Run once with the warehouse admin account: `make role`. Safe to run again.
"""

import os
import sys

import psycopg
from psycopg import sql

from olist_ai_analyst.config import get_settings


def main() -> int:
    settings = get_settings()
    admin_user = os.environ.get("POSTGRES_USER")
    admin_password = os.environ.get("POSTGRES_PASSWORD")
    agent_password = settings.agent_db_password.get_secret_value()
    if not (admin_user and admin_password and agent_password):
        print("Set POSTGRES_USER, POSTGRES_PASSWORD and AGENT_DB_PASSWORD in .env")
        return 1

    role = sql.Identifier(settings.agent_db_user)
    schema = sql.Identifier(settings.agent_db_schema)
    owner = sql.Identifier(admin_user)
    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=admin_user,
        password=admin_password,
        autocommit=True,
    ) as conn:
        exists = conn.execute(
            "select 1 from pg_roles where rolname = %s", (settings.agent_db_user,)
        ).fetchone()
        verb = sql.SQL("alter role" if exists else "create role")
        statements = [
            sql.SQL("{} {} login password {}").format(verb, role, sql.Literal(agent_password)),
            sql.SQL("alter role {} set default_transaction_read_only = on").format(role),
            sql.SQL("grant connect on database {} to {}").format(
                sql.Identifier(settings.postgres_db), role
            ),
            sql.SQL("grant usage on schema {} to {}").format(schema, role),
            sql.SQL("grant select on all tables in schema {} to {}").format(schema, role),
            # dbt drops and recreates the marts tables on every build
            sql.SQL(
                "alter default privileges for role {} in schema {} grant select on tables to {}"
            ).format(owner, schema, role),
        ]
        for statement in statements:
            conn.execute(statement)
    print(f"Role {settings.agent_db_user} can now read schema {settings.agent_db_schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

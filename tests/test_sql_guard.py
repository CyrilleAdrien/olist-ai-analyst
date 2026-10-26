import pytest

from olist_ai_analyst.sql_guard import UnsafeQueryError, extract_sql, validate_sql

TABLES = {"fct_orders", "dim_dates"}


def test_sql_is_taken_from_a_markdown_block():
    reply = "Voici la requête :\n```sql\nselect 1 from fct_orders;\n```\nBonne analyse !"
    assert extract_sql(reply) == "select 1 from fct_orders"


def test_plain_reply_is_kept():
    assert extract_sql("select 1 from fct_orders;") == "select 1 from fct_orders"


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("select * from fct_orders", "SELECT * FROM fct_orders LIMIT 1000"),
        ("select * from fct_orders limit 5", "SELECT * FROM fct_orders LIMIT 5"),
        ("select * from fct_orders limit 50000", "SELECT * FROM fct_orders LIMIT 1000"),
        (
            "with x as (select * from marts.fct_orders) select * from x",
            "WITH x AS (SELECT * FROM marts.fct_orders) SELECT * FROM x LIMIT 1000",
        ),
    ],
)
def test_select_queries_pass_with_a_row_limit(sql, expected):
    assert validate_sql(sql, TABLES) == expected


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("delete from fct_orders", "Only SELECT"),
        ("drop table fct_orders", "Only SELECT"),
        ("update fct_orders set is_late = false", "Only SELECT"),
        ("create table copy as select * from fct_orders", "Only SELECT"),
        ("select 1 from fct_orders; drop table fct_orders", "exactly one"),
        ("select * from raw.orders", "marts schema"),
        ("select * from pg_user", "Unknown table pg_user"),
        ("selec order_id frm fct_orders", "does not parse"),
    ],
)
def test_unsafe_or_invalid_queries_are_refused(sql, reason):
    with pytest.raises(UnsafeQueryError, match=reason):
        validate_sql(sql, TABLES)

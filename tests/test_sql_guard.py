import pytest

from olist_ai_analyst.sql_guard import UnsafeQueryError, extract_sql, validate_sql

TABLES = {
    "fct_orders": {"order_id", "order_date", "is_late", "customer_unique_id"},
    "dim_dates": {"date_day", "month_start"},
    "dim_customers": {"customer_unique_id", "customer_state"},
    "dim_sellers": {"seller_id", "seller_state"},
}


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


def test_unknown_column_points_to_the_table_that_holds_it():
    sql = (
        "select d.state, count(*) as late_orders from fct_orders as f"
        " join dim_dates as d on f.order_date = d.date_day where f.is_late group by d.state"
    )
    with pytest.raises(UnsafeQueryError) as error:
        validate_sql(sql, TABLES)
    assert "Column state does not exist in dim_dates" in str(error.value)
    assert "dim_customers.customer_state, dim_sellers.seller_state" in str(error.value)


def test_column_of_a_table_not_joined_is_refused():
    with pytest.raises(UnsafeQueryError, match="It exists in: dim_customers.customer_state"):
        validate_sql("select customer_state from fct_orders", TABLES)


def test_misspelled_column_gets_a_suggestion():
    with pytest.raises(UnsafeQueryError, match="Did you mean: fct_orders.order_date"):
        validate_sql("select o.order_dat from fct_orders as o", TABLES)


def test_output_aliases_can_be_reused():
    sql = "select order_date as day, count(*) as n from fct_orders group by day order by n desc"
    assert validate_sql(sql, TABLES).endswith("ORDER BY n DESC LIMIT 1000")

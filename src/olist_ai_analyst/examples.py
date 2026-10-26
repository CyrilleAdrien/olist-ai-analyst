"""Question/SQL pairs shown to the LLM as examples (few-shot).

They follow the reference queries of Olist-Analytics (bi/reference_kpis.sql). The evaluation
questions must stay different from these ones.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    question: str
    sql: str


EXAMPLES: list[Example] = [
    Example(
        question="Quel est le chiffre d'affaires total et le panier moyen ?",
        sql=(
            "select sum(items_revenue_brl) as revenue_brl,"
            " round(sum(items_revenue_brl) / count(distinct order_id), 2) as average_basket_brl"
            " from fct_orders where is_delivered"
        ),
    ),
    Example(
        question="Quelles sont les 5 catégories qui rapportent le plus ?",
        sql=(
            "select p.product_category_name_english as category, sum(i.price_brl) as revenue_brl"
            " from fct_order_items as i"
            " join dim_products as p on i.product_id = p.product_id"
            " where i.is_delivered"
            " group by 1 order by revenue_brl desc limit 5"
        ),
    ),
    Example(
        question="Quel est le chiffre d'affaires par État du client ?",
        sql=(
            "select c.customer_state, sum(o.items_revenue_brl) as revenue_brl"
            " from fct_orders as o"
            " join dim_customers as c on o.customer_unique_id = c.customer_unique_id"
            " where o.is_delivered"
            " group by c.customer_state order by revenue_brl desc"
        ),
    ),
    Example(
        question="Comment évolue le nombre de commandes par mois ?",
        sql=(
            "select d.month_start, count(*) as orders"
            " from fct_orders as o join dim_dates as d on o.order_date = d.date_day"
            " where o.is_delivered"
            " group by d.month_start order by d.month_start"
        ),
    ),
    Example(
        question="Les clients notent-ils moins bien les commandes livrées en retard ?",
        sql=(
            "select is_late, count(*) as orders, round(avg(review_score), 2) as average_score"
            " from fct_orders where is_delivered group by is_late order by is_late"
        ),
    ),
]

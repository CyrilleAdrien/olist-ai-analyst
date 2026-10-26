import datetime as dt
from decimal import Decimal

from olist_ai_analyst.chart import make_chart


def test_single_value_has_no_chart():
    assert make_chart(["revenue_brl"], [(Decimal("13221498.11"),)]) is None
    assert make_chart(["orders", "revenue_brl"], [(96478, Decimal("1.0"))]) is None


def test_dates_give_a_line_in_time_order():
    rows = [(dt.date(2017, 2, 1), Decimal("20")), (dt.date(2017, 1, 1), Decimal("10"))]
    figure = make_chart(["month_start", "revenue_brl"], rows)
    trace = figure.data[0]
    assert trace.type == "scatter"
    assert list(trace.x) == [dt.date(2017, 1, 1), dt.date(2017, 2, 1)]
    assert figure.layout.title.text == "Revenue brl by month start"


def test_labels_give_bars_largest_on_top_and_capped_at_20():
    rows = [(f"S{i:02}", i) for i in range(30)]
    trace = make_chart(["customer_state", "late_orders"], rows).data[0]
    assert trace.type == "bar"
    assert len(trace.y) == 20
    assert trace.y[-1] == "S29"  # plotly draws the last bar at the top


def test_only_the_first_measure_is_drawn():
    rows = [("SP", 1820, Decimal("12.5")), ("RJ", 1496, Decimal("14.1"))]
    figure = make_chart(["customer_state", "late_orders", "average_days"], rows)
    assert len(figure.data) == 1
    assert list(figure.data[0].x) == [1496.0, 1820.0]


def test_booleans_are_labelled_in_french():
    figure = make_chart(["is_late", "average_score"], [(False, 4.29), (True, 2.57)])
    assert set(figure.data[0].y) == {"oui", "non"}


def test_text_only_result_has_no_chart():
    assert make_chart(["category", "state"], [("bed", "SP"), ("toys", "RJ")]) is None

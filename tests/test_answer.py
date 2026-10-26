import datetime as dt
from decimal import Decimal

from langchain_core.language_models import FakeListChatModel

from olist_ai_analyst.answer import (
    EMPTY_ANSWER,
    compute_facts,
    format_table,
    fr,
    ungrounded_numbers,
    write_answer,
)

MONTHS = [(dt.date(2017, m, 1), Decimal(v)) for m, v in [(1, "111798.36"), (2, "234223.40")]]
QUESTION = "Quel est le chiffre d'affaires par mois en 2017 ?"


def test_numbers_and_states_are_written_the_french_way():
    assert fr(Decimal("13221498.11")) == "13 221 498,11"
    assert fr(96478) == "96 478"
    assert fr("AL") == "AL (Alagoas)"
    assert fr(True) == "oui"


def test_facts_give_total_average_and_extremes():
    facts = compute_facts(["month_start", "revenue_brl"], MONTHS)
    assert "Total de revenue_brl : 346 021,76" in facts
    assert "Moyenne de revenue_brl sur les 2 lignes : 173 010,88" in facts
    assert "Plus haut : 234 223,40 pour 2017-02-01" in facts


def test_rates_get_no_total():
    facts = compute_facts(["customer_state", "late_rate"], [("AL", 21.41), ("DF", 5.58)])
    assert not any(f.startswith("Total") for f in facts)
    assert "Plus bas : 5,58 pour DF (District fédéral)" in facts


def test_made_up_numbers_are_detected():
    facts = "\n".join(compute_facts(["month_start", "revenue_brl"], MONTHS))
    good = "En 2017, le CA total atteint 346 021,76 BRL, dont 234 223,40 BRL en février."
    bad = "Le chiffre d'affaires mensuel moyen est de 4 877 653,75 BRL."
    assert ungrounded_numbers(good, QUESTION, facts) == []
    assert ungrounded_numbers(bad, QUESTION, facts) == ["4 877 653,75"]


def test_made_up_answer_is_rewritten_once():
    model = FakeListChatModel(
        responses=["Le CA moyen est de 999 999 BRL.", "Le CA total est de 346 021,76 BRL."]
    )
    answer = write_answer(model, QUESTION, "select 1", ["month_start", "revenue_brl"], MONTHS)
    assert answer == "Le CA total est de 346 021,76 BRL."


def test_answer_falls_back_to_the_facts_when_the_model_keeps_inventing():
    model = FakeListChatModel(responses=["Le CA moyen est de 999 999 BRL."])
    answer = write_answer(model, QUESTION, "select 1", ["month_start", "revenue_brl"], MONTHS)
    assert answer.startswith("Voici ce que montrent les données.")
    assert "346 021,76" in answer


def test_empty_result_is_answered_without_the_model():
    model = FakeListChatModel(responses=["should not be used"])
    assert write_answer(model, "Q ?", "select 1", ["n"], []) == EMPTY_ANSWER


def test_long_results_are_cut_for_the_prompt():
    table = format_table(["state", "orders"], [("SP", i) for i in range(50)])
    assert table.count("\n") == 31
    assert table.endswith("(50 lignes au total, seules les 30 premières)")

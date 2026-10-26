from langchain_core.language_models import FakeListChatModel

from olist_ai_analyst.answer import EMPTY_ANSWER, format_table, write_answer


def test_empty_result_is_answered_without_the_model():
    model = FakeListChatModel(responses=["should not be used"])
    assert write_answer(model, "Q ?", "select 1", ["n"], []) == EMPTY_ANSWER


def test_long_results_are_cut_for_the_prompt():
    table = format_table(["state", "orders"], [("SP", i) for i in range(50)])
    assert table.count("\n") == 31
    assert table.endswith("(50 lignes au total, seules les 30 premières)")


def test_answer_is_the_model_reply():
    model = FakeListChatModel(responses=["  Le panier moyen est de 137,04 BRL.  "])
    answer = write_answer(model, "Panier moyen ?", "select 1", ["basket"], [(137.04,)])
    assert answer == "Le panier moyen est de 137,04 BRL."

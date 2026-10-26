from streamlit.testing.v1 import AppTest


def run_app():
    from langchain_core.language_models import FakeListChatModel

    from olist_ai_analyst.agent import build_agent
    from olist_ai_analyst.app import main
    from olist_ai_analyst.db import QueryResult
    from olist_ai_analyst.schema_context import Column, SchemaContext, Table

    context = SchemaContext(
        "marts", [Table("fct_orders", [Column("order_status", "text")])], {}, []
    )
    rows = [("delivered", 96478), ("shipped", 1107)]
    model = FakeListChatModel(
        responses=[
            "select order_status, count(*) as orders from fct_orders group by 1",
            "96 478 commandes sont livrées et 1 107 sont expédiées.",
        ]
    )
    agent = build_agent(model, context, lambda sql: QueryResult(["order_status", "orders"], rows))
    main(agent=agent, model_label="fake / model")


def test_app_starts_with_examples_and_a_hint():
    app = AppTest.from_function(run_app, default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Interrogez les données Olist"
    assert len(app.sidebar.button) == 4
    assert app.info[0].value.startswith("Choisissez un exemple")


def test_question_gets_an_answer_the_sql_and_the_data():
    app = AppTest.from_function(run_app, default_timeout=30).run()
    app.chat_input[0].set_value("Combien de commandes par statut ?").run()
    assert not app.exception
    assert (
        app.chat_message[1].markdown[0].value
        == "96 478 commandes sont livrées et 1 107 sont expédiées."
    )
    assert app.code[0].value.startswith("SELECT\n  order_status,")
    assert app.expander[0].label.startswith("SQL · 1 requête(s)")
    assert len(app.dataframe) == 1


def test_example_button_asks_the_question():
    app = AppTest.from_function(run_app, default_timeout=30).run()
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert (
        app.chat_message[0].markdown[0].value == "Quel est le chiffre d'affaires par mois en 2017 ?"
    )

"""Streamlit chat interface: `make app`, then http://localhost:8501."""

import time

import sqlglot
import streamlit as st

from olist_ai_analyst.agent import AgentResult, ask
from olist_ai_analyst.chart import make_chart

EXAMPLES = [
    "Quel est le chiffre d'affaires par mois en 2017 ?",
    "Quels États ont le taux de retard le plus élevé ?",
    "Quelles catégories rapportent le plus ?",
    "Les clients notent-ils moins bien les commandes en retard ?",
]


def _default_agent():
    from olist_ai_analyst.agent import build_default_agent
    from olist_ai_analyst.config import get_settings

    settings = get_settings()
    return build_default_agent(settings), f"{settings.llm_provider} / {settings.model_name}"


@st.cache_resource(show_spinner="Lecture du schéma de l'entrepôt...")
def _cached_default_agent():
    return _default_agent()


def show_result(result: AgentResult, seconds: float) -> None:
    # Streamlit reads $...$ as LaTeX
    st.markdown(result.answer.replace("$", "\\$"))
    if result.status != "ok":
        return
    figure = make_chart(result.columns, result.rows)
    if figure is not None:
        # theme=None keeps the chart's own colours, readable in light and dark mode
        st.plotly_chart(figure, theme=None, width="stretch")
    with st.expander(f"SQL · {result.attempts} requête(s) · {seconds:.1f} s"):
        st.code(sqlglot.transpile(result.sql, read="postgres", pretty=True)[0], language="sql")
    with st.expander(f"Données · {len(result.rows)} ligne(s)"):
        st.dataframe(
            {name: [row[i] for row in result.rows] for i, name in enumerate(result.columns)},
            hide_index=True,
        )


def main(agent=None, model_label: str | None = None) -> None:
    st.set_page_config(page_title="Olist AI Analyst", page_icon="📊")
    if agent is None:
        agent, model_label = _cached_default_agent()
    messages = st.session_state.setdefault("messages", [])

    with st.sidebar:
        st.header("Olist AI Analyst")
        st.write(
            "Posez une question en français sur les ventes Olist : l'agent écrit le SQL, "
            "l'exécute en lecture seule et répond avec un graphique."
        )
        st.caption(f"Modèle : {model_label}")
        st.subheader("Exemples")
        for example in EXAMPLES:
            if st.button(example, width="stretch"):
                st.session_state.pending = example
        if messages and st.button("Effacer la conversation", type="secondary"):
            messages.clear()
            st.rerun()

    st.title("Interrogez les données Olist")
    for message in messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            else:
                show_result(message["result"], message["seconds"])

    question = st.chat_input("Ex. : Quel est le panier moyen par État ?")
    question = question or st.session_state.pop("pending", None)
    if not question:
        if not messages:
            st.info("Choisissez un exemple à gauche ou écrivez votre question ci-dessous.")
        return

    messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Analyse en cours..."):
        start = time.perf_counter()
        result = ask(question, agent)
        seconds = time.perf_counter() - start
        show_result(result, seconds)
    messages.append({"role": "assistant", "result": result, "seconds": seconds})


if __name__ == "__main__":
    main()

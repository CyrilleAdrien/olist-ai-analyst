"""Write the answer in French from the query result."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

MAX_ROWS_SHOWN = 30

SYSTEM_PROMPT = """Tu es analyste de données pour Olist, une marketplace brésilienne.
On te donne une question, la requête SQL exécutée et son résultat.
Réponds en français, en 2 à 4 phrases, pour un lecteur métier :
- commence par la réponse directe, avec les chiffres clés ;
- n'utilise que les chiffres du résultat, n'invente rien ;
- écris les nombres à la française (13 221 498,11) et les montants en BRL ;
- ne parle pas du SQL ni des noms de colonnes.
"""

OUT_OF_SCOPE_ANSWER = (
    "Je ne peux répondre qu'aux questions sur les données de ventes Olist : commandes, "
    "clients, produits, vendeurs, livraisons et avis."
)
FAILED_ANSWER = (
    "Je n'ai pas réussi à écrire une requête valide pour cette question. "
    "Essayez de la reformuler, par exemple en précisant la période ou l'indicateur voulu."
)
EMPTY_ANSWER = "La requête n'a renvoyé aucune ligne : aucune donnée ne correspond à la question."


def format_table(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    lines = [" | ".join(columns)]
    lines += [" | ".join("" if v is None else str(v) for v in row) for row in rows[:MAX_ROWS_SHOWN]]
    if len(rows) > MAX_ROWS_SHOWN:
        lines.append(f"... ({len(rows)} lignes au total, seules les {MAX_ROWS_SHOWN} premières)")
    return "\n".join(lines)


def write_answer(
    llm: BaseChatModel, question: str, sql: str, columns: list[str], rows: list[tuple[Any, ...]]
) -> str:
    if not rows:
        return EMPTY_ANSWER
    prompt = (
        f"Question : {question}\n\nSQL :\n{sql}\n\n"
        f"Résultat ({len(rows)} lignes) :\n{format_table(columns, rows)}"
    )
    reply = llm.invoke([SystemMessage(SYSTEM_PROMPT), HumanMessage(prompt)])
    return str(reply.content).strip()

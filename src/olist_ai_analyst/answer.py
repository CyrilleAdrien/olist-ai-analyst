"""Write the answer in French from the query result.

Small models compute badly in their head and mix up the Brazilian state codes. So the figures
the answer may need (total, average, highest, lowest, first and last) are computed here, the
table is formatted the French way with the state names, and every number of the answer is
checked against them. An answer with a number from nowhere is rewritten once, then replaced
by a plain summary built without the model.
"""

import datetime as dt
import re
from decimal import Decimal
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

MAX_ROWS_SHOWN = 30
# A sum of rates, averages or scores means nothing: no total for these measures
NOT_ADDITIVE = ("rate", "avg", "average", "pct", "percent", "score", "days", "ratio", "mean")

STATES = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
    "CE": "Ceará", "DF": "District fédéral", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
    "PA": "Pará", "PB": "Paraíba", "PE": "Pernambouc", "PI": "Piauí", "PR": "Paraná",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima",
    "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins",
}  # fmt: skip

SYSTEM_PROMPT = """Tu es analyste de données pour Olist, une marketplace brésilienne.
On te donne une question, des faits déjà calculés et le résultat de la requête.
Réponds en français, en 2 à 4 phrases, pour un lecteur métier :
- commence par la réponse directe, avec les chiffres clés ;
- recopie les chiffres tels qu'ils sont écrits dans les faits ou le tableau ;
- ne fais aucun calcul toi-même : pas de somme, de moyenne ni d'écart qui ne soit pas fourni ;
- les montants sont en BRL ; ne parle pas du SQL ni des noms de colonnes.
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

NUMBER = re.compile(r"\d+(?:[   ]\d{3})*(?:,\d+)?|\d+(?:\.\d+)?")


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def fr(value: Any) -> str:
    """Format a value the French way: 13 221 498,11 ; 2017-01-01 stays ISO ; SP (São Paulo)."""
    if isinstance(value, bool):
        return "oui" if value else "non"
    if _is_number(value):
        number = Decimal(str(value))
        text = f"{number:,.0f}" if number == number.to_integral_value() else f"{number:,.2f}"
        return text.replace(",", " ").replace(".", ",")
    if isinstance(value, str) and value in STATES:
        return f"{value} ({STATES[value]})"
    if value is None:
        return ""
    return str(value)


def format_table(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    lines = [" | ".join(columns)]
    lines += [" | ".join(fr(v) for v in row) for row in rows[:MAX_ROWS_SHOWN]]
    if len(rows) > MAX_ROWS_SHOWN:
        lines.append(f"... ({len(rows)} lignes au total, seules les {MAX_ROWS_SHOWN} premières)")
    return "\n".join(lines)


def compute_facts(columns: list[str], rows: list[tuple[Any, ...]]) -> list[str]:
    """Figures the answer may quote, for the first numeric column, labelled by the first other."""
    facts = [f"Nombre de lignes : {len(rows)}"]
    measure = next(
        (i for i in range(len(columns)) if all(_is_number(r[i]) for r in rows if r[i] is not None)),
        None,
    )
    if measure is None or len(rows) < 2:
        return facts
    label = next((i for i in range(len(columns)) if i != measure), None)
    points = [(r[label] if label is not None else None, Decimal(str(r[measure]))) for r in rows]
    points = [p for p in points if p[1] is not None]
    name = columns[measure]
    values = [v for _, v in points]
    if not any(word in name.lower() for word in NOT_ADDITIVE):
        facts.append(f"Total de {name} : {fr(sum(values))}")
    facts.append(
        f"Moyenne de {name} sur les {len(values)} lignes : {fr(sum(values) / len(values))}"
    )
    if label is not None:
        top = max(points, key=lambda p: p[1])
        low = min(points, key=lambda p: p[1])
        facts.append(f"Plus haut : {fr(top[1])} pour {fr(top[0])}")
        facts.append(f"Plus bas : {fr(low[1])} pour {fr(low[0])}")
        if all(isinstance(p[0], dt.date) for p in points):
            first, last = min(points), max(points)
            facts.append(
                f"Premier : {fr(first[1])} ({first[0]}), dernier : {fr(last[1])} ({last[0]})"
            )
    return facts


def _as_decimal(text: str) -> Decimal:
    if "," in text or re.search(r"[   ]", text):
        text = re.sub(r"[   ]", "", text).replace(",", ".")
    return Decimal(text)


def ungrounded_numbers(answer: str, question: str, allowed: str) -> list[str]:
    """Numbers of the answer found neither in the facts, the table nor the question."""
    known = {_as_decimal(n) for n in NUMBER.findall(allowed + "\n" + question)}
    wrong = []
    for text in NUMBER.findall(answer):
        number = _as_decimal(text)
        if number <= 31 and number == number.to_integral_value():
            continue  # small counts and ranks ("les 5 premiers", "12 mois")
        if not any(abs(number - k) < Decimal("0.01") for k in known):
            wrong.append(text)
    return wrong


def fallback_answer(facts: list[str]) -> str:
    return "Voici ce que montrent les données. " + " ; ".join(facts[1:] or facts) + "."


def write_answer(
    llm: BaseChatModel, question: str, sql: str, columns: list[str], rows: list[tuple[Any, ...]]
) -> str:
    if not rows:
        return EMPTY_ANSWER
    facts = compute_facts(columns, rows)
    table = format_table(columns, rows)
    prompt = (
        f"Question : {question}\n\nFaits calculés :\n"
        + "\n".join(f"- {f}" for f in facts)
        + f"\n\nRésultat :\n{table}"
    )
    messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(prompt)]
    for _ in range(2):
        answer = str(llm.invoke(messages).content).strip()
        wrong = ungrounded_numbers(answer, question, "\n".join(facts) + "\n" + table)
        if not wrong:
            return answer
        messages += [
            AIMessage(answer),
            HumanMessage(
                f"Ces nombres ne figurent ni dans les faits ni dans le tableau : "
                f"{', '.join(wrong)}. Réécris la réponse en recopiant uniquement"
                " des chiffres fournis."
            ),
        ]
    return fallback_answer(facts)

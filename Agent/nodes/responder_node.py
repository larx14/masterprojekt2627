"""
Responder Node: formuliert aus dem fertigen State eine natürliche Antwort.
"""

import json

from Agent.state import PlanningState
from config.llm_connection import get_deepseek
from Agent.context import format_history, format_process

llm = get_deepseek()

PROMPT = """Du bist ein ERPNext-Assistent und antwortest einem Mitarbeiter im Chat.

Prozess:
{process}

Bisheriger Chatverlauf:
{history}

Aktuelle Nachricht des Mitarbeiters:
{instruction}

Ergebnis (einzige Quelle für ERP-Daten):
{data}

Regeln:
- ERP-Daten nur aus dem Ergebnis verwenden, nichts erfinden.
- Gefundene Datensätze übersichtlich als Liste ausgeben.
- Fehlen Informationen oder wurde abgebrochen: kurz erklären und konkret nachfragen.
- Ist die Nachricht keine Aufgabe (Smalltalk, eine Aussage): natürlich darauf
  eingehen, statt sie als Auftrag zu behandeln.
- Keine technischen Begriffe (Step, Tool, JSON, Plan).
- Kein Markdown (keine Sternchen, keine Überschriften). Aufzählungen mit "- ".
- Duze den Mitarbeiter. Antworte auf Deutsch und kurz.
"""


def responder(state: PlanningState) -> dict:

    data = {
        "outcome": (state.get("final_result") or {}).get("outcome"),
        "missing_info": state.get("missing_info"),
        "abort_reason": state.get("abort_reason"),
        "results": [
            (r.get("result") or {}).get("data")
            for r in (state.get("step_results") or {}).values()
        ],
    }

    prompt = PROMPT.format(
        process=format_process(state),
        history=format_history(state),
        instruction=state.get("instruction", ""),
        data=json.dumps(data, ensure_ascii=False, default=str),
    )

    try:
        text = llm.invoke(prompt).content.strip()
    except Exception:
        text = (state.get("final_result") or {}).get("message", "")

    return {"response": text}
"""
Responder Node: formuliert aus dem fertigen State eine natürliche Antwort.
"""

import json

from Agent.state import PlanningState
from config.llm_connection import get_deepseek

llm = get_deepseek()

PROMPT = """Du bist ein ERPNext-Assistent und antwortest einem Mitarbeiter im Chat.

Anfrage des Mitarbeiters:
{instruction}

Ergebnis (einzige Datenquelle):
{data}

Regeln:
- Verwende nur Daten aus dem Ergebnis, erfinde nichts.
- Gefundene Datensätze übersichtlich als Liste ausgeben.
- Fehlen Informationen oder wurde abgebrochen: kurz erklären und konkret nachfragen.
- Keine technischen Begriffe (Step, Tool, JSON, Plan).
- Antworte auf Deutsch und kurz.
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
        instruction=state.get("instruction", ""),
        data=json.dumps(data, ensure_ascii=False, default=str),
    )

    try:
        text = llm.invoke(prompt).content.strip()
    except Exception:
        text = (state.get("final_result") or {}).get("message", "")

    return {"response": text}
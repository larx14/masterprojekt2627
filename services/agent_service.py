# Startet den LangGraph-Agenten und meldet den Fortschritt:
# - Statuszeile (ActivityService) bei jedem Node-Start
# - Chatnachricht (notify) nach jedem ausgeführten Schritt
# AKTUELL NUR get_read_tool_specs()

from Agent.graph import graph
from Agent.tools.read_tools import get_read_tool_specs
from services.activity_service import ActivityService


NODE_LABELS = {
    "planner":             "Plane die Aufgabe …",
    "plan_validator":      "Validiere den Plan …",
    "condition_evaluator": "Prüfe Bedingungen: {step} …",
    "skip_step":           "Überspringe: {step} (Bedingung nicht erfüllt) …",
    "action_preparer":     "Bereite vor: {step} …",
    "governance_gate":     "Prüfe Richtlinien und Autonomiestufe …",
    "human_review":        "Warte auf Freigabe: {step} …",
    "executor":            "Führe aus: {step} …",
    "evaluator":           "Prüfe das Ergebnis …",
    "replanner":           "Passe den Plan an …",
    "finalizer":           "Schließe ab …",
    "responder":           "Formuliere die Antwort …",
}

# Nodes, die sich auf einen konkreten Planschritt beziehen
STEP_NODES = {
    "condition_evaluator", "skip_step", "action_preparer",
    "governance_gate", "human_review", "executor", "evaluator",
}


def _current_step(state: dict):
    plan = state.get("plan") or []
    index = state.get("current_step") or 0
    if 0 <= index < len(plan):
        return index, plan[index]
    return index, None


def _label(node: str, state: dict) -> str | None:
    template = NODE_LABELS.get(node)
    if not template:
        return None

    index, step = _current_step(state)
    description = (step or {}).get("description") or "nächster Schritt"
    text = template.format(step=description)

    plan = state.get("plan") or []
    if step and node in STEP_NODES:
        text = f"Schritt {index + 1}/{len(plan)} · {text}"

    return text


def _executor_message(update: dict, state: dict) -> str | None:
    """Text für die Chatnachricht nach einem Executor-Lauf."""

    _, step = _current_step(state)
    if not step:
        return None

    record = (update.get("step_results") or {}).get(step.get("id"))
    if not record:
        return None  # z. B. execution_blocked: kein Ergebnis

    description = step.get("description") or step.get("tool")

    if record.get("status") == "completed":
        text = f"✓ {description} – wurde erfolgreich ausgeführt."
        result = record.get("result")
        if isinstance(result, dict) and "count" in result:
            text += f" ({result['count']} Treffer)"
        return text

    return f"✗ {description} – ist fehlgeschlagen: {record.get('reason') or 'unbekannter Fehler'}"


def _final_text(state: dict) -> str:
    """Abschlussnachricht. Später: Text des Responder-Nodes."""

    if state.get("response"):
        return state["response"]

    final = state.get("final_result") or {}
    return final.get("message") or "Die Anfrage wurde verarbeitet."


class AgentService:

    @staticmethod
    def process_instruction(instruction: str, process_id: str | None = None, notify=None):

        if not instruction or not instruction.strip():
            raise ValueError("Instruction darf nicht leer sein.")

        initial_state = {
            "instruction": instruction,
            "available_tools": get_read_tool_specs(),
        }

        state = dict(initial_state)

        for mode, chunk in graph.stream(
            initial_state,
            stream_mode=["tasks", "updates", "values"],
        ):
            # Kompletter State nach jedem Superstep
            if mode == "values":
                state = chunk

            # Node startet -> Statuszeile aktualisieren
            elif mode == "tasks" and "input" in chunk:
                label = _label(chunk.get("name"), state)
                if label and process_id:
                    ActivityService.update(process_id, label)

            # Executor fertig -> Chatnachricht
            elif mode == "updates" and notify and "executor" in chunk:
                text = _executor_message(chunk["executor"] or {}, state)
                if text:
                    notify(text)

        return {
            "message": _final_text(state),
            "status": state.get("status"),
            "plan": state.get("plan", []),
            "step_results": state.get("step_results", {}),
            "missing_info": state.get("missing_info"),
            "abort_reason": state.get("abort_reason"),
        }
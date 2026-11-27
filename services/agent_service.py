# Startet den LangGraph-Agenten und meldet den Fortschritt:
# - Statuszeile (ActivityService) bei jedem Node-Start
# - Chatnachricht (notify) nach jedem ausgeführten Schritt
# - Freigabefrage im Chat, wenn der Graph in human_review pausiert
# - Antwort auf die Freigabe setzt den pausierten Lauf fort
# AKTUELL NUR get_read_tool_specs()

import re
import uuid

from langgraph.types import Command

from Agent.tools.read_tools import get_read_tool_specs
from Governance.chat_format import format_escalation
from services.activity_service import ActivityService
from config.db_connection import db
from services.process_service import ProcessService
from Agent.graph import graph, tool_registry


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

# --------------------------------------------------
# RESET_FIELDS
# --------------------------------------------------
# Ein Chat (Prozess) nutzt immer denselben Thread im Checkpointer.
# Startet auf diesem Thread ein NEUER Lauf (z. B. nach einer Rückfrage
# oder einer Folgefrage), lädt LangGraph automatisch den alten State.
# Ohne Zurücksetzen würden alte Werte weiterleben, z. B.:
#   - step_results enthält noch "step1" -> Executor blockiert
#     ("Step 'step1' already has an execution record")
#   - current_step zeigt auf einen alten Schritt
#   - response / final_result enthalten die alte Antwort
# Deshalb werden diese Ausführungsdaten bei jedem neuen Lauf geleert.
# NICHT zurückgesetzt werden:
#   - history (wird per operator.add angehängt = kompletter Verlauf)
#   - chat_history / process_context / autonomy_level (kommen frisch
#     aus _load_context / facts)
RESET_FIELDS = {
    "goal": "",
    "proposed_steps": [],
    "plan": [],
    "current_step": 0,
    "missing_info": [],
    "abort_reason": "",
    "plan_valid": False,
    "validation_errors": [],
    "artifacts": {},
    "step_results": {},
    "condition_result": "",
    "condition_reason": "",
    "prepared_action": {},
    "status": "",
    "replan_count": 0,
    "replan_reason": "",
    "execution_error": "",
    "final_result": {},
    "response": "",
    "expected_state": {},
    "verification_result": {},
    "governance": {},
    "candidates": [],
}

# --------------------------------------------------
# Schlüsselwörter für _parse_review_answer()
# --------------------------------------------------
# Einfache Regeln statt LLM: schnell, kostenlos und nachvollziehbar.
# Es wird auf ganze Wörter geprüft (nicht auf Teilstrings), damit z. B.
# "Japan" nicht als "ja" erkannt wird.
REJECT_WORDS = ("abbrechen", "ablehnen", "nein", "nicht", "stopp", "stop")
APPROVE_WORDS = (
    "freigeben", "freigabe", "ja", "jo", "jep", "ok", "okay", "passt", "mach",
    "darfst", "einverstanden", "go", "yes", "klar", "genehmigt",
)


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

    # Fehlertext kürzen: Bei ERPNext-Fehlern steckt im reason der komplette
    # HTTP-Body mit Traceback. Wir zeigen nur die eigentliche Meldung, z. B.
    # "ERPNext: Please enter Reqd by Date".
    reason = record.get("reason") or "unbekannter Fehler"
    match = re.search(r'"exception":\s*"([^"]+)"', reason)
    if match:
        reason = "ERPNext: " + match.group(1).split(": ", 1)[-1]

    return f"✗ {description} – ist fehlgeschlagen: {reason[:200]}"


def _final_text(state: dict) -> str:
    """Abschlussnachricht (Text des Responder-Nodes)."""

    if state.get("response"):
        return state["response"]

    final = state.get("final_result") or {}
    return final.get("message") or "Die Anfrage wurde verarbeitet."


MAX_HISTORY = 10


def _load_context(process_id: str | None) -> dict:
    """Chatverlauf und Prozessdaten für den State laden."""

    if not process_id:
        return {}

    rows = db.execute(
        """
        SELECT role, content
        FROM public.chat_messages
        WHERE process_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (process_id, MAX_HISTORY + 1),
    ) or []

    # Neueste zuerst -> umdrehen; die letzte ist die aktuelle Nachricht
    # (wurde vor dem Start schon gespeichert) und steckt bereits in "instruction".
    history = [{"role": r[0], "content": r[1]} for r in reversed(rows)][:-1]

    process = ProcessService.get_process(process_id)
    # get_process: (id, name, description, status, created_at, autonomy_level)

    return {
        "chat_history": history,
        "process_context": {
            "name": process[1] if process else None,
            "description": process[2] if process else None,
        },
        "autonomy_level": (process[5] if process else None) or "L1",
    }


def _pending_interrupt(config: dict):
    """
    Prüft, ob der Thread dieses Prozesses gerade auf eine Antwort
    des Menschen wartet (human_review hat interrupt() aufgerufen).

    Rückgabe:
        das Payload-Dict, das human_review an interrupt() übergeben hat
        (Grund, Vorschlag, Optionen, Risiko ...), oder None.

    Ablauf:
        1. graph.get_state(config) lädt über den Checkpointer den letzten
           gespeicherten Stand dieses Threads.
        2. snapshot.next enthält die Nodes, die als Nächstes laufen würden.
           - leer  -> der letzte Lauf ist bis END durchgelaufen
                      (oder es gab noch nie einen Lauf) -> nichts wartet
           - gefüllt -> der Lauf wurde unterbrochen
        3. snapshot.tasks enthält die offenen Tasks. Hat einer davon
           Interrupts, wartet er auf eine Antwort. Dessen .value ist
           genau das Payload aus human_review.
    """

    snapshot = graph.get_state(config)

    # Kein offener Node -> Lauf abgeschlossen, neuer Lauf möglich
    if not snapshot.next:
        return None

    # Den Task suchen, der durch interrupt() angehalten wurde
    for task in snapshot.tasks or []:
        if task.interrupts:
            return task.interrupts[0].value

    return None


def _parse_review_answer(text: str, payload: dict) -> dict:
    """
    Übersetzt die freie Chatantwort des Mitarbeiters in das Format,
    das human_review erwartet (siehe Agent/nodes/human_review_node.py):

        {"action": "approve"}
        {"action": "select", "index": 1}
        {"action": "reject", "comment": "..."}
        {"action": "provide_info", "info": {...}}

    Das Ergebnis wird mit Command(resume=...) an den pausierten Graph
    übergeben und kommt in human_review als Rückgabewert von interrupt()
    an.

    Eine unpassende Antwort ist kein Fehler: human_review prüft die
    Antwort selbst (validate_answer) und ruft bei einem Fehler erneut
    interrupt() mit einem Hinweis auf -> die Frage erscheint nochmal im
    Chat (max. 3 Versuche, danach gilt der Schritt als abgelehnt).
    """

    # In Kleinbuchstaben und einzelne Wörter zerlegen
    lowered = text.strip().lower()
    words = lowered.replace(",", " ").replace(".", " ").replace("!", " ").split()

    # 1. Ablehnen zuerst prüfen, damit "nicht freigeben" oder
    #    "nein, nicht machen" nicht als Freigabe gewertet wird.
    if any(w in REJECT_WORDS for w in words):
        return {"action": "reject", "comment": text}

    # 2. Hat das Governance Gate fehlende Angaben gemeldet (needs_human),
    #    ist approve nicht erlaubt. Die Antwort wird als zusätzliche
    #    Information weitergegeben; human_review schreibt sie in facts
    #    und der Schritt wird im action_preparer neu vorbereitet.
    if payload.get("type") == "needs_human":
        return {"action": "provide_info", "info": {"antwort": text}}

    # 3. Eine Zahl wählt eine der angebotenen Optionen, z. B. "2" oder
    #    "Option 2". Im Chat zählen wir ab 1, im Code ab 0 -> -1.
    for w in words:
        if w.isdigit():
            return {"action": "select", "index": int(w) - 1}

    # 4. Zustimmung, z. B. "ja", "freigeben", "passt", "darfst du machen"
    #    startswith("freig") fängt auch Tippfehler wie "freigebe" ab.
    if any(w in APPROVE_WORDS or w.startswith("freig") for w in words):
        return {"action": "approve"}

    # 5. Nicht erkannt -> bewusst ungültige Aktion, damit human_review
    #    mit einem Hinweis erneut nachfragt.
    return {"action": "unknown", "comment": text}


class AgentService:

    @staticmethod
    def process_instruction(instruction: str, process_id: str | None = None, notify=None):

        if not instruction or not instruction.strip():
            raise ValueError("Instruction darf nicht leer sein.")

        # --------------------------------------------------
        # Thread bestimmen
        # --------------------------------------------------
        # Ein Chat = ein Prozess = ein Thread im Checkpointer.
        # Über diese thread_id speichert und lädt LangGraph den State.
        # Nur ohne process_id (z. B. in Tests) wird eine zufällige ID
        # vergeben, damit sich solche Läufe nicht gegenseitig stören.
        thread_id = process_id or f"no-process:{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}

        # --------------------------------------------------
        # Fortsetzen oder neu starten?
        # --------------------------------------------------
        payload = _pending_interrupt(config)

        if payload is not None:
            # FALL A: Der Thread wartet in human_review.
            # Die Chatnachricht ist die Antwort auf die Freigabefrage.
            # Command(resume=...) setzt den Graph genau dort fort; in
            # human_review gibt interrupt() dann diese Antwort zurück.
            # Es wird KEIN neuer Plan erstellt, der gespeicherte State
            # (Plan, erledigte Schritte ...) bleibt erhalten.
            graph_input = Command(resume=_parse_review_answer(instruction, payload))

            # Aktuellen State laden, damit Statuszeile und Executor-
            # Meldungen sofort die richtigen Schrittbeschreibungen kennen.
            state = dict(graph.get_state(config).values)

        else:
            # FALL B: Nichts wartet -> neuer Lauf auf demselben Thread.
            # RESET_FIELDS leert die Ausführungsdaten des letzten Laufs,
            # danach kommen die neue Nachricht, die Tools und der frisch
            # geladene Kontext (Chatverlauf, Prozessdaten).
            graph_input = {
                **RESET_FIELDS,
                "instruction": instruction,
                "available_tools": tool_registry.get_specs(),
                **_load_context(process_id),
            }
            state = dict(graph_input)

        # Wird gesetzt, falls der Graph in diesem Lauf (erneut) pausiert
        interrupt_payload = None

        # --------------------------------------------------
        # Graph ausführen und Events auswerten
        # --------------------------------------------------
        # graph_input ist entweder der Start-State (Fall B) oder
        # Command(resume=...) (Fall A). Der Stream liefert Tupel
        # (mode, chunk), je nach stream_mode:
        #   "values"  -> kompletter State nach jedem Schritt
        #   "tasks"   -> ein Node startet / ist fertig
        #   "updates" -> Änderungen eines Nodes, bzw. "__interrupt__"
        for mode, chunk in graph.stream(
            graph_input,
            config=config,
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

            # Graph pausiert:
            # human_review ruft interrupt(payload) auf. LangGraph bricht den
            # Node ab, speichert den State im Checkpointer und schickt als
            # letztes Event {"__interrupt__": (Interrupt(value=payload),)}.
            # Danach endet der Stream ganz normal (kein Fehler).
            # .value ist das Payload-Dict aus human_review.
            elif mode == "updates" and "__interrupt__" in chunk:
                interrupt_payload = chunk["__interrupt__"][0].value

            # Executor fertig -> Chatnachricht
            elif mode == "updates" and notify and "executor" in chunk:
                text = _executor_message(chunk["executor"] or {}, state)
                if text:
                    notify(text)

        # --------------------------------------------------
        # Ergebnis zurückgeben
        # --------------------------------------------------
        # Pausiert: Aus dem Payload wird mit format_escalation()
        # (Governance/chat_format.py) eine deutsche Freigabefrage gebaut.
        # ChatService speichert sie wie jede andere Antwort im Chat.
        # Merken muss sich niemand etwas: Der Checkpointer weiß, dass
        # dieser Thread wartet, und _pending_interrupt() findet das bei
        # der nächsten Nachricht wieder.
        if interrupt_payload is not None:
            return {
                "message": format_escalation(interrupt_payload),
                "status": "waiting_for_human",
                "thread_id": thread_id,
            }

        # Lauf bis END durchgelaufen: Antwort des Responders zurückgeben
        return {
            "message": _final_text(state),
            "status": state.get("status"),
            "plan": state.get("plan", []),
            "step_results": state.get("step_results", {}),
            "missing_info": state.get("missing_info"),
            "abort_reason": state.get("abort_reason"),
            "thread_id": thread_id,
        }
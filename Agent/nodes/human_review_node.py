"""
LangGraph node: human review via interrupt().

The graph pauses here; the runner (see channels.py) sends the
payload to the escalation channel and resumes the graph with
Command(resume=answer). Requires a checkpointer.

Answer format:
    {"action": "approve"}
    {"action": "select", "index": 1}
    {"action": "edit",   "args": {...}}
    {"action": "reject", "comment": "..."}
    {"action": "provide_info", "info": {...}}   # adds facts, step is prepared again

An invalid answer is not an error: the node asks again
(up to MAX_ATTEMPTS) and treats the step as rejected after that.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from langgraph.types import interrupt

from Governance import decision_log


ANSWERS = ("approve", "select", "edit", "reject", "provide_info")
MAX_ATTEMPTS = 3


def validate_answer(answer: Any, g: dict[str, Any]) -> str | None:
    """Return an error message, or None if the answer is usable."""

    if not isinstance(answer, dict) or answer.get("action") not in ANSWERS:
        return f"Unknown answer. Allowed: {', '.join(ANSWERS)}."

    kind = answer["action"]

    # Incomplete proposals must not be executed unchanged.
    if g.get("decision") == "needs_human" and kind in ("approve", "select"):
        return "Information is missing: use provide_info, edit or reject."

    if kind == "select":
        options = g.get("options", [])
        index = answer.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(options):
            return f"Invalid option index {index!r}."
        if not options[index].get("executable", True):
            return "The selected option is not an executable action."

    if kind == "edit" and not isinstance(answer.get("args"), dict):
        return "edit requires 'args' as an object."

    if kind == "provide_info" and not isinstance(answer.get("info"), dict):
        return "provide_info requires 'info' as an object."

    return None


def human_review(state: dict[str, Any]) -> dict:

    g = state.get("governance", {})
    proposal = g.get("proposal", {})

    payload = {
        "type": g.get("decision"),           # escalate | needs_human
        "trigger": state.get("trigger"),
        "process_id": state.get("process_id"),
        "step_id": g.get("step_id"),
        "reason": g.get("reason"),
        "confidence": g.get("conf_consistency"),
        "risk": g.get("risk"),
        "autonomy_level": g.get("autonomy_level"),
        "rule_hits": g.get("rule_hits", []),
        "proposal": proposal,
        "options": g.get("options", []),
        "missing_info": state.get("missing_info", []),
    }

    answer, error = None, None

    for _ in range(MAX_ATTEMPTS):
        answer = interrupt({**payload, "error": error} if error else payload)
        error = validate_answer(answer, g)
        if error is None:
            break
    else:
        answer = {"action": "reject", "comment": f"No valid answer: {error}"}

    kind = answer["action"]
    action, facts = None, None

    if kind == "approve":
        action = proposal
    elif kind == "select":
        action = g["options"][answer["index"]]["action"]
    elif kind == "edit":
        action = {**proposal, "args": answer["args"]}
    elif kind == "provide_info":
        facts = {**state.get("facts", {}), **answer["info"]}

    corrected = kind != "approve"

    if g.get("log_id"):
        try:
            decision_log.update(g["log_id"], decision_log.to_json({
                "human_action": kind,
                "corrected": corrected,
                "final_action": action,
            }))
        except Exception:
            pass

    if action is not None:
        status = "approved"
    elif facts is not None:
        status = "info_provided"
    else:
        status = "rejected"

    update = {
        "prepared_action": action or {},
        "governance": {**g, "human_action": kind, "corrected": corrected,
                       "human_comment": answer.get("comment")},
        "status": status,
        "history": [{
            "event": "human_review",
            "step_id": g.get("step_id"),
            "answer": kind,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }

    if facts is not None:
        update.update({"facts": facts, "candidates": [], "missing_info": []})

    return update


def route_after_review(
    state: dict[str, Any]
) -> Literal["execute", "prepare", "stop"]:

    status = state.get("status")

    if status == "approved":
        return "execute"
    if status == "info_provided":
        return "prepare"
    return "stop"

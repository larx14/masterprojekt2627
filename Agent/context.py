"""
Formatiert Chatverlauf und Prozesskontext für LLM-Prompts.
"""

from Agent.state import PlanningState


def format_history(state: PlanningState, max_chars: int = 500) -> str:
    lines = [
        f"{'Mitarbeiter' if m.get('role') == 'user' else 'Assistent'}: "
        f"{(m.get('content') or '')[:max_chars]}"
        for m in state.get("chat_history") or []
    ]
    return "\n".join(lines) or "(leer)"


def format_process(state: PlanningState) -> str:
    ctx = state.get("process_context") or {}
    return (
        f"Name: {ctx.get('name') or '-'}\n"
        f"Beschreibung: {ctx.get('description') or '-'}\n"
        f"Autonomiestufe: {state.get('autonomy_level') or '-'}"
    )
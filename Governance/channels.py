"""
Escalation channels and the runner that connects them
to interrupted graphs.

The graph does not know the channel. The runner reads the
interrupt payload, picks a channel by trigger and resumes
the graph with the human answer. New channel = new class.
"""

import json
from typing import Any, Callable

from langgraph.types import Command


class EscalationChannel:
    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Show the escalation and return the human answer."""
        raise NotImplementedError


class ConsoleChannel(EscalationChannel):
    """Terminal prompt. For tests and demos."""

    def ask(self, payload):
        print("\n=== ESKALATION ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        print("Optionen: approve | select <index> | reject")
        raw = input("> ").strip().split()

        if not raw or raw[0] == "approve":
            return {"action": "approve"}
        if raw[0] == "select" and len(raw) > 1:
            return {"action": "select", "index": int(raw[1])}
        return {"action": "reject", "comment": " ".join(raw[1:])}


class ScriptedChannel(EscalationChannel):
    """Returns predefined answers. For automated test runs."""

    def __init__(self, answers: list[dict[str, Any]]):
        self.answers = list(answers)
        self.payloads: list[dict[str, Any]] = []

    def ask(self, payload):
        self.payloads.append(payload)
        return self.answers.pop(0)


class ChatChannel(EscalationChannel):
    """Later: answer the user in the chat that triggered the process."""

    def ask(self, payload):
        raise NotImplementedError("ChatChannel is not implemented yet.")


class ERPChannel(EscalationChannel):
    """Later: post a comment/ToDo in ERPNext and set process_list status."""

    def ask(self, payload):
        raise NotImplementedError("ERPChannel is not implemented yet.")


def default_resolver(payload: dict[str, Any]) -> EscalationChannel:
    return {"chat": ChatChannel, "auto": ERPChannel}.get(
        payload.get("trigger"), ConsoleChannel
    )()


def run_with_escalation(
    graph,
    state: dict[str, Any],
    config: dict[str, Any],
    resolver: Callable[[dict[str, Any]], EscalationChannel] = default_resolver,
    max_rounds: int = 20,
) -> dict[str, Any]:
    """
    Run the graph and handle interrupts until it finishes.
    config needs a thread_id: {"configurable": {"thread_id": "..."}}
    """

    result = graph.invoke(state, config)

    for _ in range(max_rounds):
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        if not interrupts:
            return result

        payload = interrupts[0].value
        answer = resolver(payload).ask(payload)
        result = graph.invoke(Command(resume=answer), config)

    raise RuntimeError("Too many escalation rounds.")

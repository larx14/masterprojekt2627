
from Agent.graph import graph
from Agent.tools.read_tools import get_read_tool_specs


class AgentService:

    @staticmethod
    def process_instruction(instruction: str):

        if not instruction or not instruction.strip():
            raise ValueError("Instruction darf nicht leer sein.")

        # Tool-Katalog für den Planner
        available_tools = get_read_tool_specs()

        initial_state = {
            "instruction": instruction,
            "available_tools": available_tools,
        }

        # LangGraph ausführen
        result = graph.invoke(initial_state)

        return {
            "status": result.get("status"),
            "plan": result.get("plan", []),
            "missing_info": result.get("missing_info"),
            "abort_reason": result.get("abort_reason"),
        }

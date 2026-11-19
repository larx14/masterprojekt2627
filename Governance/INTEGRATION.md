# Governance-Layer: Einbindung in den Agenten

Der Governance-Layer sitzt zwischen `action_preparer` und `executor`.
Die Nodes liegen in `Agent/nodes/governance_gate_node.py` und `Agent/nodes/human_review_node.py`,
die Logik in `Governance/`.
Er ist fertig und getestet (`Tests/test_governance.py`, `Tests/test_governance_graph.py`),
braucht aber kleine Änderungen im bestehenden Agent-Code, damit er im echten Graph läuft.

## Ablauf

```
condition_evaluator ──true──► action_preparer ──► governance_gate ─┬─ sample   ──► action_preparer (adaptiv nachsampeln)
                                                                    ├─ execute  ──► executor
                                                                    ├─ review   ──► human_review ─┬─ execute ──► executor
                                                                    │                             ├─ prepare ──► action_preparer (neue Infos)
                                                                    │                             └─ stop    ──► END
                                                                    └─ stop     ──► END
```

## Vertrag

| Feld | Wer schreibt | Wer liest | Inhalt |
|---|---|---|---|
| `candidates` | action_preparer (hängt an) | governance_gate | Liste von Kandidaten, siehe unten |
| `n_requested` | governance_gate | action_preparer | Anzahl zusätzlicher Samples (0 = keine) |
| `prepared_action` | governance_gate / human_review | executor | wie bisher: `{step_id, tool, args, reason, confidence}` |
| `governance` | governance_gate / human_review | executor, Logging | Konfidenz, Risiko, Regeln, Entscheidung, `log_id` |
| `status` | alle | Routing | Gate: `sampling`, `auto`, `escalate`, `needs_human`; Review: `approved`, `rejected`, `info_provided` |
| `autonomy_level`, `trigger`, `process_id`, `scenario_id` | Aufrufer beim Start | Gate, Log | Kontext |

**Kandidat** (ein Eintrag pro Sample):

```python
{
    "tool": "create_purchase_order",
    "args": {...},
    "missing_info": [],      # nicht leer -> eigener Cluster "MISSING"
    "valid": True,           # False bei Parse-/Schemafehler -> Cluster "INVALID"
    "errors": [],
    "reason": "...",
    "confidence": 0.9,       # verbalisierte Konfidenz des LLM
}
```

## Änderungen

### 1. `Agent/state.py`

```python
from Governance.state_fields import GovernanceFields

class PlanningState(GovernanceFields, total=False):
    ...  # bestehende Felder unverändert
```

LangGraph verwirft Keys, die nicht im State-Schema stehen. Ohne diese Zeile kommen `candidates` & Co. nicht an.

### 2. `config/llm_connection.py`

```python
def get_deepseek(temperature: float = 0):
    return ChatDeepSeek(model="deepseek-chat", api_key=DEEPSEEK_API_KEY, temperature=temperature)
```

### 3. `Agent/nodes/action_preparer_node.py`

- Vorab-Checks (Plan validiert, Step-Index, Tool-Spec) bleiben, wie sie sind.
- Der LLM-Call wird N-mal ausgeführt statt einmal, parallel per `.batch()`.
- Einzelne Samples brechen **nicht** mehr ab, sondern werden als Kandidat gespeichert.

```python
from Governance.config import get_config
from Governance.risk import initial_samples

GOV_CFG = get_config()

def to_candidate(response, tool_name, parameters) -> dict:
    action = response.get("parsed")
    if action is None:
        return {"tool": tool_name, "args": {}, "missing_info": [], "valid": False,
                "errors": [str(response.get("parsing_error"))], "reason": "", "confidence": None}
    errors = []
    if action.tool != tool_name:
        errors.append(f"Tool mismatch: {action.tool}")
    if not action.missing_info:
        errors += validate_arguments(action.args, parameters)
    return {"tool": action.tool, "args": action.args, "missing_info": action.missing_info,
            "valid": not errors, "errors": errors,
            "reason": action.reason, "confidence": action.confidence}

def action_preparer(state):
    ...  # bestehende Vorab-Checks, prompt bauen

    n = state.get("n_requested") or initial_samples(selected_tool, GOV_CFG)
    temperature = GOV_CFG["sampling"]["temperature"] if n > 1 else 0
    structured_llm = get_deepseek(temperature).with_structured_output(
        PreparedAction, method="json_mode", include_raw=True)

    responses = structured_llm.batch([prompt] * n, return_exceptions=True)
    new = [
        to_candidate(r, tool_name, parameters) if isinstance(r, dict)
        else {"tool": tool_name, "args": {}, "missing_info": [], "valid": False,
              "errors": [f"{type(r).__name__}: {r}"], "reason": "", "confidence": None}
        for r in responses
    ]

    return {
        "candidates": (state.get("candidates") or []) + new,
        "n_requested": 0,
        "status": "action_prepared",
        "history": [make_event("candidates_prepared", step_id=step["id"], n=len(new))],
    }
```

Hinweis: Das LLM nicht mehr auf Modulebene erzeugen, sondern im Node. So lassen sich die Tests ohne API-Key importieren.

### 4. `Agent/graph.py`

```python
from Agent.nodes.governance_gate_node import governance_gate, route_after_governance
from Agent.nodes.human_review_node import human_review, route_after_review

builder.add_node("governance_gate", governance_gate)
builder.add_node("human_review", human_review)
builder.add_node("executor", executor)

# statt: builder.add_edge("action_preparer", END)
builder.add_edge("action_preparer", "governance_gate")
builder.add_conditional_edges("governance_gate", route_after_governance, {
    "sample": "action_preparer", "execute": "executor",
    "review": "human_review", "stop": END})
builder.add_conditional_edges("human_review", route_after_review, {
    "execute": "executor", "prepare": "action_preparer", "stop": END})
builder.add_edge("executor", "condition_evaluator")   # nächster Schritt
```

`human_review` nutzt `interrupt()` und braucht deshalb einen Checkpointer:
`build_planning_graph(checkpointer)` mit dem `PostgresSaver` aus `config/db_connection.py`
(in Tests `InMemorySaver`).

### 5. Executor (neu) und `skip_step`

- Führt **nur** `prepared_action` aus, und nur wenn `governance["decision"] == "auto"`
  oder `governance["human_action"]` eine Freigabe ist (Status `auto` bzw. `approved`).
- Schreibt `step_results[step_id] = {"status": "completed", "result": {...}}`
  mit den `result_fields` des Tools.
- Setzt `candidates = []`, `n_requested = 0`, `prepared_action = {}` und zählt `current_step` hoch.
- `skip_step` setzt ebenfalls `candidates = []`.

### 6. Tool-Specs

Optional `"risk": "read" | "draft" | "submit" | "payment"` pro Tool. Fehlt es, leitet
`Governance/risk.py` das Risiko aus Tool-Name, `doctype` und `docstatus` ab.

### 7. Tests

`Tests/test_action_preparer.py` prüft heute `prepared_action` und `status = needs_human`
direkt am Preparer. Nach der Änderung liefert der Preparer `candidates`; die Entscheidung
trifft das Gate. Die Tests müssen entsprechend auf `candidates` umgestellt werden.

## Ausführen mit Eskalation

```python
from Governance.channels import run_with_escalation

config = {"configurable": {"thread_id": process_id}}
result = run_with_escalation(graph, initial_state, config)
```

Kanäle (`Governance/channels.py`): `ConsoleChannel` ist fertig; `ChatChannel` (Trigger `chat`)
und `ERPChannel` (Trigger `auto`) sind Platzhalter.

## Konfiguration

`Governance/config.yaml`: Autonomiestufe, Sampling (5 → max. 10), Schwellen pro Risiko (L2),
harte Regeln, ignorierte Freitextfelder.

Harte Regeln brauchen Fakten im State, z. B.
`facts = {"known_suppliers": [...], "last_prices": {"MEHL-550": 0.8}}`.
Fehlen sie, greift die Regel nicht.

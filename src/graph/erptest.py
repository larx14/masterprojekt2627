from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict, total=False):
    customer: str
    quantity: int
    customer_found: bool
    stock: int
    result: str


FAKE_CUSTOMERS = {"TEST-Müller GmbH"}
FAKE_STOCK = 50


def check_customer(state: State):
    found = state["customer"] in FAKE_CUSTOMERS
    print(f"[check_customer] gefunden: {found}")
    return {"customer_found": found}


def check_stock(state: State):
    print(f"[check_stock] Bestand: {FAKE_STOCK}")
    return {"stock": FAKE_STOCK}


def create_draft(state: State):
    print("[create_draft]")
    return {"result": f"Draft angelegt: {state['quantity']} Stück für {state['customer']}"}


def escalate(state: State):
    print("[escalate]")
    if not state.get("customer_found"):
        reason = "Kunde unbekannt"
    else:
        reason = "Lagerbestand zu niedrig"
    return {"result": f"Eskaliert an Mensch: {reason}"}


def route_after_customer(state: State) -> str:
    return "check_stock" if state["customer_found"] else "escalate"


def route_after_stock(state: State) -> str:
    return "create_draft" if state["stock"] >= state["quantity"] else "escalate"


builder = StateGraph(State)
builder.add_node("check_customer", check_customer)
builder.add_node("check_stock", check_stock)
builder.add_node("create_draft", create_draft)
builder.add_node("escalate", escalate)

builder.add_edge(START, "check_customer")
builder.add_conditional_edges("check_customer", route_after_customer, ["check_stock", "escalate"])
builder.add_conditional_edges("check_stock", route_after_stock, ["create_draft", "escalate"])
builder.add_edge("create_draft", END)
builder.add_edge("escalate", END)

graph = builder.compile()


if __name__ == "__main__":
    tests = [
        {"customer": "TEST-Müller GmbH", "quantity": 10},
        {"customer": "TEST-Müller GmbH", "quantity": 500},
        {"customer": "Unbekannt AG", "quantity": 10},
    ]
    for t in tests:
        print("\n---", t)
        out = graph.invoke(t)
        print("Ergebnis:", out["result"])
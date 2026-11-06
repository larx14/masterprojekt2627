from typing import TypedDict
from langgraph.graph import StateGraph, START, END
# Unser Claude-Modell importieren
from src.config import llm 

# =====================================
# 1. STATE DEFINIEREN
# =====================================
class AgentState(TypedDict):
    user_input: str
    category: str
    response: str

# =====================================
# 2. NODE 1: ANFRAGE ANALYSIEREN
# =====================================
def analyze_request(state: AgentState):
    prompt = f"""
    Analysiere die folgende User-Anfrage:
    {state["user_input"]}
    Entscheide, ob es sich um eine allgemeine Frage
    oder eine Frage zu ERPNext handelt.
    Antworte ausschließlich mit:
    GENERAL
    oder
    ERP
    """
    result = llm.invoke(prompt)
    category = result.content.strip().upper()
    print(f"Erkannte Kategorie: {category}")
    return {
        "category": category
    }

# =====================================
# 3. NODE 2: ALLGEMEINE ANTWORT
# =====================================
def general_response(state: AgentState):
    prompt = f"""
    Beantworte diese allgemeine Frage freundlich
    und verständlich:
    {state["user_input"]}
    """
    result = llm.invoke(prompt)
    return {
        "response": result.content
    }

# =====================================
# 4. NODE 3: ERPNEXT ANTWORT
# =====================================
def erp_response(state: AgentState):
    prompt = f"""
    Du bist ein ERPNext-Experte.
    Beantworte die folgende Frage ausführlich
    und fachlich korrekt:
    {state["user_input"]}
    """
    result = llm.invoke(prompt)
    return {
        "response": result.content
    }

# =====================================
# 5. ROUTING-FUNKTION
# =====================================
def route_request(state: AgentState):
    if state["category"] == "ERP":
        return "erp_response"
    return "general_response"

# =====================================
# 6. GRAPH ERSTELLEN
# =====================================
builder = StateGraph(AgentState)
# Nodes registrieren
builder.add_node("analyze_request", analyze_request)
builder.add_node("general_response", general_response)
builder.add_node("erp_response", erp_response)
# Startpunkt
builder.add_edge(START, "analyze_request")
# Bedingte Weiterleitung
builder.add_conditional_edges(
    "analyze_request",
    route_request,
    {
        "general_response": "general_response",
        "erp_response": "erp_response"
    }
)
# Beide Antwort-Nodes führen zum Ende
builder.add_edge("general_response", END)
builder.add_edge("erp_response", END)
# Graph kompilieren
graph = builder.compile()

if __name__ == "__main__":
 
    user_input = input("Was möchtest du wissen? ")
 
    result = graph.invoke({
        "user_input": user_input
    })
 
    print("\nAntwort des Agenten:")
    print(result["response"])
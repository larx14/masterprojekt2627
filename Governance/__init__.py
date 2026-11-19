"""
Governance-Layer des AI Employee.

Entscheidet vor jeder Aktion, ob der Agent autonom handeln darf
oder an einen Menschen eskaliert. Grundlage ist eine Konsistenz-
Konfidenz nach dem Sampling-Ansatz aus arXiv 2411.02454 (Stufe 1:
Anteil des größten Clusters), kombiniert mit Risikoklassen,
harten Regeln und konfigurierbaren Autonomiestufen (L1-L3).

Die LangGraph-Nodes liegen in Agent/nodes/
(governance_gate_node.py, human_review_node.py) und nutzen dieses Paket.
Bis auf decision_log und channels sind alle Module reine Funktionen
ohne LLM-, ERP- oder DB-Zugriff.
"""

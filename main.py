from src.config import llm 

# Claude direkt verwenden
antwort = llm.invoke(
    "Erkläre mir in zwei Sätzen, was LangChain ist."
)
 
print(antwort.content)
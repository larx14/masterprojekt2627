from src.config import model

# Claude direkt verwenden
antwort = model.invoke(
    "Erkläre mir in zwei Sätzen, was LangChain ist."
)
 
print(antwort.content)
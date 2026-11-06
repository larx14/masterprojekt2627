import os
from dotenv import load_dotenv


# 1. .env-Datei laden
load_dotenv()


# 2. Claude-Modell über LangChain importieren
from langchain_anthropic import ChatAnthropic


# 3. Claude-Modell konfigurieren
# Der API-Key wird automatisch aus ANTHROPIC_API_KEY gelesen.
model = ChatAnthropic(
    model="claude-haiku-5-5",
    max_tokens=300
)

# 4. Eine Nachricht an Claude senden
antwort = model.invoke(
    "Erkläre mir in zwei Sätzen, was LangChain ist."
)

# 5. Den Antworttext ausgeben
print(antwort.content)
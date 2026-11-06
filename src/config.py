import os
from dotenv import load_dotenv, find_dotenv
from langchain_anthropic import ChatAnthropic

# 1. .env-Datei laden
load_dotenv(find_dotenv())

# 2. API-Key überprüfen
api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    print("FEHLER: Kein Anthropic API-Key gefunden!")
 

# 3. Claude-Modell konfigurieren
# Der API-Key wird automatisch aus ANTHROPIC_API_KEY gelesen.
model = ChatAnthropic(
    model="claude-haiku-5-5",
    max_tokens=300
)


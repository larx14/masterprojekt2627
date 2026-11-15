import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.llm_client import get_deepseek

def test_deepseek():

    print("\nTeste DeepSeek-Verbindung...")

    try:
        llm = get_deepseek()

        response = llm.invoke(
            "Antworte mit: DeepSeek Verbindung erfolgreich!"
        )

        print("DeepSeek Antwort:")
        print(response.content)

        return True

    except Exception as e:
        print(f"DeepSeek Fehler: {e}")
        return False



def main():

    deepseek_ok = test_deepseek()

    print("\n---------- TESTERGEBNIS ----------")
    print(f"DeepSeek: {'OK' if deepseek_ok else 'FEHLER'}")


if __name__ == "__main__":
    main()

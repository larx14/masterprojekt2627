import sys
from pathlib import Path


# Das hier muss man hinzufügen, weil er sonst nicht die Module aus anderen Projektordnern findet
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

import Process.process_manager as process_manager


def main():
    process_id = process_manager.create_process(
        "Test Process",
        "A simple test process."
    )

    print(f"Created process with ID: {process_id}")


if __name__ == "__main__":
    main()

##"python test_db_connection.py" in der Konsole ausführen, um den Test zu starten.#
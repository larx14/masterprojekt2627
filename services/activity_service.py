"""
Flüchtiger Fortschrittsstatus pro Prozess (eine Zeile im Frontend).
Liegt im Speicher: reicht für einen uvicorn-Worker, geht bei Neustart verloren.
"""

import threading

_lock = threading.Lock()
_activity: dict[str, dict] = {}


class ActivityService:

    @staticmethod
    def start(process_id: str, text: str = "Starte …") -> None:
        with _lock:
            _activity[process_id] = {"running": True, "text": text}

    @staticmethod
    def update(process_id: str, text: str) -> None:
        with _lock:
            _activity[process_id] = {"running": True, "text": text}

    @staticmethod
    def finish(process_id: str) -> None:
        with _lock:
            _activity[process_id] = {"running": False, "text": ""}

    @staticmethod
    def is_running(process_id: str) -> bool:
        with _lock:
            return _activity.get(process_id, {}).get("running", False)

    @staticmethod
    def get(process_id: str) -> dict:
        with _lock:
            return dict(_activity.get(process_id, {"running": False, "text": ""}))
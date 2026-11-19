"""
Decision log: one record per governance decision.

Backends are exchangeable. Default is Postgres (table
public.decision_log, see sql/001_decision_log.sql);
tests use the in-memory backend.

    from Governance import decision_log
    decision_log.set_backend(decision_log.MemoryBackend())
"""

import json
import uuid
from typing import Any, Protocol


COLUMNS = (
    "process_id", "thread_id", "scenario_id", "step_id", "tool", "risk",
    "autonomy_level", "trigger", "n_samples", "distribution",
    "conf_consistency", "conf_verbal", "threshold", "rule_hits",
    "decision", "reason", "chosen_action", "final_action",
    "human_action", "corrected", "correct",
)

JSON_COLUMNS = {"distribution", "rule_hits", "chosen_action", "final_action"}
UPDATABLE = {"final_action", "human_action", "corrected", "correct"}


class Backend(Protocol):
    def write(self, record: dict[str, Any]) -> str: ...
    def update(self, log_id: str, fields: dict[str, Any]) -> None: ...


class MemoryBackend:
    """Keeps records in a list. For tests and dry runs."""

    def __init__(self):
        self.records: dict[str, dict[str, Any]] = {}

    def write(self, record):
        log_id = str(uuid.uuid4())
        self.records[log_id] = {"id": log_id, **record}
        return log_id

    def update(self, log_id, fields):
        self.records[log_id].update(fields)


def _valid_uuid(value) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


class PostgresBackend:
    """Writes to public.decision_log via the shared db client."""

    def _db(self):
        # Imported lazily: config.db_connection connects on import.
        from config.db_connection import db
        return db

    @staticmethod
    def _value(column, value):
        if column in JSON_COLUMNS and value is not None:
            from psycopg.types.json import Jsonb
            return Jsonb(value)
        if column == "process_id":
            return _valid_uuid(value)
        return value

    def write(self, record):
        columns = [c for c in COLUMNS if c in record]
        values = [self._value(c, record[c]) for c in columns]
        placeholders = ", ".join(["%s"] * len(columns))

        rows = self._db().execute(
            f"INSERT INTO public.decision_log ({', '.join(columns)}) "
            f"VALUES ({placeholders}) RETURNING id",
            values,
        )
        return str(rows[0][0])

    def update(self, log_id, fields):
        fields = {k: v for k, v in fields.items() if k in UPDATABLE}
        if not fields:
            return

        assignments = ", ".join(f"{column} = %s" for column in fields)
        values = [self._value(c, v) for c, v in fields.items()]

        self._db().execute(
            f"UPDATE public.decision_log SET {assignments} WHERE id = %s",
            [*values, log_id],
        )


_backend: Backend = PostgresBackend()


def set_backend(backend: Backend) -> None:
    global _backend
    _backend = backend


def get_backend() -> Backend:
    return _backend


def write(record: dict[str, Any]) -> str:
    return _backend.write(record)


def update(log_id: str, fields: dict[str, Any]) -> None:
    _backend.update(log_id, fields)


def to_json(value: Any) -> Any:
    """Make values JSON-safe before logging."""
    return json.loads(json.dumps(value, default=str))

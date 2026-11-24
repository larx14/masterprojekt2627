

#In dieser Klasse befinden sich Methoden, die einen neuen Prozesse in der Datenbank anlegen oder auslesen#

import uuid
from config.db_connection import db

def create_process_id():
    return str(uuid.uuid4())

def create_process(process_name, description=None):
    """Erstellt einen neuen Beschaffungsprozess."""

    process_id = create_process_id()

    db.execute(
        """
        INSERT INTO public.process_list (
            id,
            name,
            description,
            status
        )
        VALUES (%s, %s, %s, %s)
        """,
        (process_id, process_name, description, "ACTIVE")
    )

    return process_id
def get_all_processes():
    """Gibt alle gespeicherten Prozesse zurück."""

    return db.execute(
        """
        SELECT
            id,
            name,
            description,
            status,
            created_at
        FROM public.process_list
        ORDER BY created_at DESC
        """
    )


def get_process(process_id):
    """Lädt einen Prozess anhand seiner ID."""

    result = db.execute(
        """
        SELECT
            id,
            name,
            description,
            status,
            created_at
        FROM public.process_list
        WHERE id = %s
        """,
        (process_id,)
    )

    return result[0] if result else None


def update_status(process_id, status):
    """Aktualisiert den Status eines Prozesses."""

    db.execute(
        """
        UPDATE public.process_list
        SET status = %s
        WHERE id = %s
        """,
        (status, process_id)
    )
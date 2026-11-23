import uuid

from config.db_connection import db


VALID_STATUSES = {"ACTIVE", "INACTIVE"}
VALID_AUTONOMY_LEVELS = {"L1", "L2", "L3"}


class ProcessService:

    # Spaltenreihenfolge (wichtig für process_routes):
    # 0 id, 1 name, 2 description, 3 status, 4 created_at, 5 autonomy_level

    @staticmethod
    def create_process(process_name, description=None, autonomy_level="L1"):
        """Erstellt einen neuen Prozess."""

        if autonomy_level not in VALID_AUTONOMY_LEVELS:
            raise ValueError(f"Ungültige Autonomiestufe: {autonomy_level}")

        process_id = str(uuid.uuid4())

        db.execute(
            """
            INSERT INTO public.process_list (
                id,
                name,
                description,
                status,
                autonomy_level
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (process_id, process_name, description, "ACTIVE", autonomy_level)
        )

        return process_id

    @staticmethod
    def get_all_processes():
        """Lädt alle Prozesse."""

        return db.execute(
            """
            SELECT id, name, description, status, created_at, autonomy_level
            FROM public.process_list
            ORDER BY created_at DESC
            """
        )

    @staticmethod
    def get_process(process_id):
        """Lädt einen einzelnen Prozess."""

        result = db.execute(
            """
            SELECT id, name, description, status, created_at, autonomy_level
            FROM public.process_list
            WHERE id = %s
            """,
            (process_id,)
        )

        return result[0] if result else None

    @staticmethod
    def update_status(process_id, status):
        """Aktualisiert den Prozessstatus und gibt den neuen Status zurück."""

        status = (status or "").strip().upper()

        if status not in VALID_STATUSES:
            raise ValueError(f"Ungültiger Status: {status}")

        result = db.execute(
            """
            UPDATE public.process_list
            SET status = %s
            WHERE id = %s
            RETURNING status
            """,
            (status, process_id)
        )

        # result ist leer, wenn keine Zeile aktualisiert wurde
        return result[0][0] if result else None
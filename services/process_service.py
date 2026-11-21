
import uuid

from config.db_connection import db


class ProcessService:

    @staticmethod
    def create_process(process_name, description=None):
        """Erstellt einen neuen Prozess."""

        process_id = str(uuid.uuid4())

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

    @staticmethod
    def get_all_processes():
        """Lädt alle Prozesse."""

        return db.execute(
            """
            SELECT id, name, description, status, created_at
            FROM public.process_list
            ORDER BY created_at DESC
            """
        )

    @staticmethod
    def get_process(process_id):
        """Lädt einen einzelnen Prozess."""

        result = db.execute(
            """
            SELECT id, name, description, status, created_at
            FROM public.process_list
            WHERE id = %s
            """,
            (process_id,)
        )

        return result[0] if result else None

    @staticmethod
    def update_status(process_id, status):
        """Aktualisiert den Prozessstatus."""

        db.execute(
            """
            UPDATE public.process_list
            SET status = %s
            WHERE id = %s
            """,
            (status, process_id)
        )

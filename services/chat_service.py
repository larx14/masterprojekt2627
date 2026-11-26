
import json

from config.db_connection import db
from services.agent_service import AgentService
from services.activity_service import ActivityService


class ChatService:

    @staticmethod
    def save_message(process_id, role, content):
        db.execute(
            """
            INSERT INTO public.chat_messages (
                process_id, role, content
            )
            VALUES (%s, %s, %s)
            """,
            (process_id, role, content)
        )

    @staticmethod
    def get_messages(process_id):
        return db.execute(
            """
            SELECT id, role, content, created_at
            FROM public.chat_messages
            WHERE process_id = %s
            ORDER BY created_at ASC
            """,
            (process_id,)
        )

    @staticmethod
    def run_agent(process_id, message):
        """
        Läuft im Hintergrund. Die User-Nachricht wurde schon gespeichert.
        """

        def notify(text):
            ChatService.save_message(process_id, "assistant", text)

        try:
            result = AgentService.process_instruction(
                message,
                process_id=process_id,
                notify=notify,
            )
            notify(result["message"])

        except Exception as exc:
            notify(f"Bei der Verarbeitung ist ein Fehler aufgetreten: {exc}")

        finally:
            # Erst NACH der letzten Nachricht beenden, damit das
            # Frontend beim letzten Abruf alles sieht.
            ActivityService.finish(process_id)

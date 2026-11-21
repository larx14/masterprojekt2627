
import json

from config.db_connection import db
from services.agent_service import AgentService


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
    def send_message(process_id, message):

        # 1. User-Nachricht speichern
        ChatService.save_message(
            process_id,
            "user",
            message
        )

        try:
            # 2. LangGraph aufrufen
            result = AgentService.process_instruction(message)

            # 3. Agent-Antwort lesbar aufbereiten
            response = json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str
            )

            # 4. Agent-Antwort speichern
            ChatService.save_message(
                process_id,
                "assistant",
                response
            )

            return {
                "status": "success",
                "response": response,
                "agent_result": result
            }

        except Exception as exc:

            # Fehler ebenfalls im Chat sichtbar machen
            error_message = (
                f"Bei der Verarbeitung ist ein Fehler aufgetreten: {exc}"
            )

            ChatService.save_message(
                process_id,
                "assistant",
                error_message
            )

            raise

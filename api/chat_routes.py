
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.process_service import ProcessService
from services.chat_service import ChatService


router = APIRouter(prefix="/processes", tags=["Chat"])


class ChatMessage(BaseModel):
    message: str




@router.post("/{process_id}/messages")
def send_message(process_id: str, request: ChatMessage):

    process = ProcessService.get_process(process_id)

    if not process:
        raise HTTPException(
            status_code=404,
            detail="Process not found"
        )

    try:
        return ChatService.send_message(
            process_id,
            request.message
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Agent-Verarbeitung fehlgeschlagen: {exc}"
        )



@router.get("/{process_id}/messages")
def get_chat_messages(process_id: str):

    try:
        process = ProcessService.get_process(process_id)

        if not process:
            raise HTTPException(
                status_code=404,
                detail="Prozess nicht gefunden."
            )

        rows = ChatService.get_messages(process_id)

        return [
            {
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "created_at": str(row[3]) if row[3] else None,
            }
            for row in rows
        ]

    except HTTPException:
        raise

    except Exception as e:
        print("Fehler beim Laden der Chatnachrichten:", e)

        raise HTTPException(
            status_code=500,
            detail="Chatnachrichten konnten nicht geladen werden."
        )

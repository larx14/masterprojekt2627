from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.process_service import ProcessService
from services.chat_service import ChatService
from services.activity_service import ActivityService

router = APIRouter(prefix="/processes", tags=["Chat"])


class ChatMessage(BaseModel):
    message: str




@router.post("/{process_id}/messages")
def send_message(process_id: str, request: ChatMessage, background_tasks: BackgroundTasks):

    process = ProcessService.get_process(process_id)

    if not process:
        raise HTTPException(status_code=404, detail="Process not found")

    if ActivityService.is_running(process_id):
        raise HTTPException(
            status_code=409,
            detail="Der Agent arbeitet noch an der vorherigen Anfrage."
        )

    ChatService.save_message(process_id, "user", request.message)

    # Vor dem Start setzen, damit das erste Polling schon "running" sieht
    ActivityService.start(process_id, "Starte …")
    background_tasks.add_task(ChatService.run_agent, process_id, request.message)

    return {"status": "started"}



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

@router.get("/{process_id}/activity")
def get_activity(process_id: str):
    return ActivityService.get(process_id)

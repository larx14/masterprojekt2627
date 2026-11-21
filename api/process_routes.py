
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.process_service import ProcessService


router = APIRouter(prefix="/processes", tags=["Processes"])


class ProcessCreate(BaseModel):
    name: str
    description: str | None = None


class StatusUpdate(BaseModel):
    status: str


@router.get("")
def get_all_processes():
    try:
        rows = ProcessService.get_all_processes()

        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "status": row[3],
                "created_at": str(row[4]) if row[4] else None,
            }
            for row in rows
        ]

    except Exception as e:
        print("Fehler beim Laden der Prozesse:", e)
        raise HTTPException(
            status_code=500,
            detail="Prozesse konnten nicht geladen werden."
        )


@router.post("")
def create_process(data: ProcessCreate):
    if not data.name.strip():
        raise HTTPException(
            status_code=400,
            detail="Der Prozessname darf nicht leer sein."
        )

    try:
        process_id = ProcessService.create_process(
            data.name.strip(),
            data.description
        )

        return {
            "id": process_id,
            "name": data.name.strip(),
            "status": "ACTIVE"
        }

    except Exception as e:
        print("Fehler beim Erstellen des Prozesses:", e)
        raise HTTPException(
            status_code=500,
            detail="Prozess konnte nicht erstellt werden."
        )


@router.get("/{process_id}")
def get_process(process_id: str):
    try:
        row = ProcessService.get_process(process_id)

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Prozess nicht gefunden."
            )

        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "status": row[3],
            "created_at": str(row[4]) if row[4] else None,
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Fehler beim Laden des Prozesses:", e)
        raise HTTPException(
            status_code=500,
            detail="Prozess konnte nicht geladen werden."
        )


@router.patch("/{process_id}/status")
def update_process_status(process_id: str, data: StatusUpdate):
    try:
        process = ProcessService.get_process(process_id)

        if not process:
            raise HTTPException(
                status_code=404,
                detail="Prozess nicht gefunden."
            )

        ProcessService.update_status(process_id, data.status)

        return {
            "success": True,
            "status": data.status
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Fehler beim Aktualisieren des Status:", e)
        raise HTTPException(
            status_code=500,
            detail="Status konnte nicht aktualisiert werden."
        )

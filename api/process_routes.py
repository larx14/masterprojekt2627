from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.process_service import ProcessService, VALID_STATUSES


router = APIRouter(prefix="/processes", tags=["Processes"])


class ProcessCreate(BaseModel):
    name: str
    description: str | None = None
    autonomy_level: Literal["L1", "L2", "L3"] = "L1"


class StatusUpdate(BaseModel):
    status: str


def row_to_dict(row):
    """Wandelt eine DB-Zeile in ein JSON-fähiges Dict um."""
    return {
        "id": str(row[0]),
        "name": row[1],
        "description": row[2],
        "status": (row[3] or "INACTIVE").upper(),
        "created_at": str(row[4]) if row[4] else None,
        "autonomy_level": row[5] or "L1",
    }


@router.get("")
def get_all_processes():
    try:
        rows = ProcessService.get_all_processes()
        return [row_to_dict(row) for row in rows]

    except Exception as e:
        print("Fehler beim Laden der Prozesse:", e)
        raise HTTPException(
            status_code=500,
            detail="Prozesse konnten nicht geladen werden."
        )


@router.post("")
def create_process(data: ProcessCreate):
    name = data.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Der Prozessname darf nicht leer sein."
        )

    description = (data.description or "").strip() or None

    try:
        process_id = ProcessService.create_process(
            name,
            description,
            data.autonomy_level
        )

        return {
            "id": process_id,
            "name": name,
            "description": description,
            "status": "ACTIVE",
            "autonomy_level": data.autonomy_level
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

        return row_to_dict(row)

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
    new_status = (data.status or "").strip().upper()

    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Status muss ACTIVE oder INACTIVE sein."
        )

    try:
        updated_status = ProcessService.update_status(process_id, new_status)

        if updated_status is None:
            raise HTTPException(
                status_code=404,
                detail="Prozess nicht gefunden."
            )

        return {
            "success": True,
            "id": process_id,
            "status": updated_status
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Fehler beim Aktualisieren des Status:", e)
        raise HTTPException(
            status_code=500,
            detail="Status konnte nicht aktualisiert werden."
        )
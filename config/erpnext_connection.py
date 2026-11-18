
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from Process.process_manager import (
    create_process,
    get_all_processes,
    get_process,
    update_status,
)

# --------------------------------------------------
# KONFIGURATION
# --------------------------------------------------

load_dotenv()

ERPNext_URL = os.getenv("ERPNEXT_URL", "").rstrip("/")

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------

app = FastAPI(
    title="AI Process API",
    description="API zur Verbindung von ERPNext mit LangGraph",
    version="1.0.0",
)

# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("ERPNEXT_URL", "").rstrip("/")
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
# --------------------------------------------------
# DATENMODELLE
# --------------------------------------------------

class ProcessCreate(BaseModel):
    name: str
    description: str | None = None


class StatusUpdate(BaseModel):
    status: str


# --------------------------------------------------
# BASIS-ENDPUNKTE
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "AI Process API läuft",
        "status": "online"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# --------------------------------------------------
# PROZESSVERWALTUNG
# --------------------------------------------------

@app.get("/processes")
def api_get_all_processes():

    try:
        rows = get_all_processes()

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

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Prozesse konnten nicht geladen werden."
        )


@app.post("/processes")
def api_create_process(data: ProcessCreate):

    if not data.name.strip():
        raise HTTPException(
            status_code=400,
            detail="Der Prozessname darf nicht leer sein."
        )

    try:
        process_id = create_process(
            data.name.strip(),
            data.description
        )

        return {
            "id": process_id,
            "name": data.name,
            "status": "ACTIVE"
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Prozess konnte nicht erstellt werden."
        )


@app.get("/processes/{process_id}")
def api_get_process(process_id: str):

    try:
        row = get_process(process_id)

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

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Prozess konnte nicht geladen werden."
        )


@app.patch("/processes/{process_id}/status")
def api_update_status(process_id: str, data: StatusUpdate):

    allowed_statuses = {
        "ACTIVE",
        "COMPLETED",
        "CANCELLED"
    }

    if data.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Ungültiger Status."
        )

    try:
        if not get_process(process_id):
            raise HTTPException(
                status_code=404,
                detail="Prozess nicht gefunden."
            )

        update_status(process_id, data.status)

        return {
            "success": True,
            "process_id": process_id,
            "status": data.status
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Status konnte nicht aktualisiert werden."
        )

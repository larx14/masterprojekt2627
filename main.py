


##### AKTUELL DAS HIER IN DER MIAN KLASSE DAMIT ERPNEXT VERBINDUNG MIT FASTAPI FUNKTIONIERT #####


import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.process_routes import router as process_router
from api.chat_routes import router as chat_router


# Umgebungsvariablen laden
load_dotenv()

# FastAPI erstellen
app = FastAPI(
    title="AI Process API",
    description="API zur Verbindung von ERPNext mit LangGraph",
    version="1.0.0",
)

# CORS konfigurieren
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("ERPNEXT_URL", "").rstrip("/")
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# Basis-Endpunkte
@app.get("/")
def root():
    return {
        "message": "AI Process API läuft",
        "status": "online"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# Router registrieren
app.include_router(process_router)
app.include_router(chat_router)

import os

from dotenv import find_dotenv, load_dotenv
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row, tuple_row
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv(find_dotenv())
 

conninfo = make_conninfo(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

# Eine gemeinsame Verbindung für alles
pool = ConnectionPool(
    conninfo=conninfo,
    min_size=1,
    max_size=10,
    open=True,
    kwargs={
        "autocommit": True,
        "row_factory": dict_row,  
        "prepare_threshold": 0,
    },
)

# Speichert den Agenten-Zustand
checkpointer = PostgresSaver(pool)
checkpointer.setup()

class DatabaseClient:
    def execute(self, query, params=None):
        with pool.connection() as conn:
            # tuple_row: deine Abfragen liefern weiter Tupel, main.py muss nicht geändert werden
            with conn.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(query, params)
                if cursor.description:
                    return cursor.fetchall()
                return None


db = DatabaseClient()
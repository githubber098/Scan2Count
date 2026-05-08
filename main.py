import os
from fastapi import FastAPI
from dotenv import load_dotenv
import psycopg2

# Load environment variables from .env file (only used in local development;
# in production, Render injects env vars directly)
load_dotenv()

app = FastAPI()


@app.get("/")
def root():
    return {"status": "ok", "message": "Hello, future food app"}


@app.get("/health")
def health():
    """
    Health check that verifies our backend can connect to the Supabase database.
    Returns the Postgres version on success.
    """
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        return {
            "status": "error",
            "message": "DATABASE_URL environment variable is not set",
        }

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        postgres_version = cur.fetchone()[0]
        cur.close()
        conn.close()

        return {
            "status": "ok",
            "database": "connected",
            "postgres_version": postgres_version,
            "message":"You Rock!",
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "connection failed",
            "error": str(e),
        }
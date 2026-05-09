import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
import psycopg2

from routers import auth as auth_router
from routers import profile as profile_router
from dependencies import get_optional_user

load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
jinja_env = Environment(loader=FileSystemLoader("templates"))

def render(name: str, context: dict, status_code: int = 200):
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(**context), status_code=status_code)

# Register routers
app.include_router(auth_router.router)
app.include_router(profile_router.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Landing page. If the user is already logged in, show them a link to home.
    If not, show the signup/login landing.
    """
    user = get_optional_user(request)
    return render("index.html", {"request": request, "user": user.email if user else None})


@app.get("/health")
def health():
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
            "message": "You Rock!",
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "connection failed",
            "error": str(e),
        }

@app.get("/auth/confirm", response_class=HTMLResponse)
async def auth_confirm(request: Request):
    """
    Landing page for email confirmation links.
    Reads the JWT fragment client-side and POSTs it to /auth/session.
    """
    return render("auth/confirm.html", {"request": request})
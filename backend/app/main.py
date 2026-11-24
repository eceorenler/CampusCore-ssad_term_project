"""CampusCore API entry point. Run with: uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.db.session import engine
from app.jobs.no_show import NoShowWorker
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.check_ins.router import router as check_ins_router
from app.modules.reservations.router import router as reservations_router
from app.modules.resources.router import router as resources_router

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = NoShowWorker(settings.no_show_job_interval_seconds) if settings.run_no_show_job else None
    if worker:
        worker.start()
    yield
    if worker:
        worker.stop()


app = FastAPI(
    title="CampusCore API",
    version="1.3.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

register_error_handlers(app)

# Local development only: production serves frontend and API from one origin
# through a reverse proxy, so CORS is not needed there (spec section 7).
if not settings.is_production and settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit list, never "*" with credentials
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", settings.csrf_header_name],
    )


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


api = APIRouter(prefix="/api/v1")


@api.get("/health", tags=["system"])
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


api.include_router(auth_router)
api.include_router(resources_router)
api.include_router(reservations_router)
api.include_router(check_ins_router)
api.include_router(admin_router)

app.include_router(api)

from fastapi import FastAPI
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.health import router as health_router

app = FastAPI(
    title=settings.app_name,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)

register_exception_handlers(app)
app.include_router(health_router)


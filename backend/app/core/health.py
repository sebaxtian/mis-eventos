import logging
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session
from app.core.cache import CacheClient, get_cache_client
from app.core.database import get_session
from app.core.exceptions import error_responses

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    redis: Literal["ok", "degraded"]


@router.get(
    "/health",
    response_model=HealthResponse,
    responses=error_responses(503),
)
def get_health(
    session: Session = Depends(get_session),
    cache: CacheClient = Depends(get_cache_client),
) -> HealthResponse:
    try:
        session.exec(text("SELECT 1")).one()
    except SQLAlchemyError as exc:
        logger.error("Database health check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de base de datos no disponible",
        ) from exc

    redis_ok = cache.ping()
    return HealthResponse(
        status="ok",
        database="ok",
        redis="ok" if redis_ok else "degraded",
    )

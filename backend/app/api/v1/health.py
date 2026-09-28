from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
        db_status = "connected"
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        db_status = "disconnected"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "db": db_status,
        "version": "0.1.0",
        "env": settings.APP_ENV,
    }

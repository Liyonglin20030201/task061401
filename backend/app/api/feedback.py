from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Feedback
from app.schemas import FeedbackCreate, FeedbackOut, FeedbackStats
from app.services.feedback_service import create_feedback, get_feedback_stats
from app.core.dependencies import get_current_user, require_role
from app.models import UserRole

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("/", response_model=FeedbackOut, status_code=201)
async def submit_feedback(
    data: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_feedback(data, user.id, db)


@router.get("/stats", response_model=FeedbackStats)
async def feedback_stats(
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    return await get_feedback_stats(db)

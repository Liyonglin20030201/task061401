from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserRole
from app.schemas import TopQuestionOut, SatisfactionTrendOut, AnalyticsAccuracyOut, KnowledgeGapOut
from app.services.analytics_service import (
    get_top_questions, get_satisfaction_trend,
    get_accuracy_stats, get_knowledge_gaps, cluster_questions_batch,
)
from app.core.dependencies import require_role

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/top-questions", response_model=list[TopQuestionOut])
async def top_questions(
    kb_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    return await get_top_questions(db, kb_id, days, limit)


@router.get("/satisfaction-trend", response_model=SatisfactionTrendOut)
async def satisfaction_trend(
    kb_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    data = await get_satisfaction_trend(db, kb_id, days)
    return SatisfactionTrendOut(data=data)


@router.get("/accuracy", response_model=AnalyticsAccuracyOut)
async def accuracy_stats(
    kb_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    return await get_accuracy_stats(db, kb_id, days)


@router.get("/knowledge-gaps", response_model=list[KnowledgeGapOut])
async def knowledge_gaps(
    kb_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    return await get_knowledge_gaps(db, kb_id, days, limit)


@router.post("/cluster-questions", status_code=202)
async def trigger_clustering(
    background_tasks: BackgroundTasks,
    kb_id: Optional[UUID] = Query(None),
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    background_tasks.add_task(cluster_questions_batch, db, kb_id)
    return {"status": "clustering started"}

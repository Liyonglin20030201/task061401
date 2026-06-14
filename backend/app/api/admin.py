from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    User, UserRole, SensitiveWord, SystemConfig,
    Document, Conversation, Message, Feedback, DocStatus
)
from app.schemas import (
    UserOut, SensitiveWordCreate, SensitiveWordOut,
    SystemConfigUpdate, DashboardStats
)
from app.services.sensitive_filter import sensitive_filter
from app.core.dependencies import require_role
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ===== User Management =====

@router.get("/users", response_model=list[UserOut])
async def list_users(
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: UUID,
    role: str,
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundException("User not found")
    target.role = UserRole(role)
    await db.flush()
    return {"status": "updated", "new_role": role}


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: UUID,
    is_active: bool,
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundException("User not found")
    target.is_active = is_active
    await db.flush()
    return {"status": "updated", "is_active": is_active}


# ===== Sensitive Words =====

@router.get("/config/sensitive-words", response_model=list[SensitiveWordOut])
async def list_sensitive_words(
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SensitiveWord).order_by(SensitiveWord.id))
    return result.scalars().all()


@router.post("/config/sensitive-words", response_model=SensitiveWordOut, status_code=201)
async def add_sensitive_word(
    data: SensitiveWordCreate,
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    word = SensitiveWord(word=data.word, category=data.category)
    db.add(word)
    await db.flush()
    # Reload filter
    await sensitive_filter.load_words(db)
    return word


@router.delete("/config/sensitive-words/{word_id}", status_code=204)
async def remove_sensitive_word(
    word_id: int,
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SensitiveWord).where(SensitiveWord.id == word_id))
    word = result.scalar_one_or_none()
    if not word:
        raise NotFoundException("Sensitive word not found")
    await db.delete(word)
    await sensitive_filter.load_words(db)


# ===== System Config =====

@router.get("/config/system")
async def get_system_config(
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()
    return {c.key: c.value for c in configs}


@router.put("/config/system")
async def update_system_config(
    data: SystemConfigUpdate,
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == data.key))
    config = result.scalar_one_or_none()
    if config:
        config.value = data.value
    else:
        config = SystemConfig(key=data.key, value=data.value)
        db.add(config)
    await db.flush()
    return {"status": "updated"}


# ===== Dashboard =====

@router.get("/stats/dashboard", response_model=DashboardStats)
async def dashboard_stats(
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    users_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    docs_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    convs_count = (await db.execute(select(func.count(Conversation.id)))).scalar() or 0
    msgs_count = (await db.execute(select(func.count(Message.id)))).scalar() or 0
    avg_rating = float((await db.execute(select(func.avg(Feedback.rating)))).scalar() or 0)

    # Documents by status
    status_counts = {}
    for status in DocStatus:
        count = (await db.execute(
            select(func.count(Document.id)).where(Document.status == status)
        )).scalar() or 0
        status_counts[status.value] = count

    return DashboardStats(
        total_users=users_count,
        total_documents=docs_count,
        total_conversations=convs_count,
        total_messages=msgs_count,
        avg_rating=round(avg_rating, 2),
        documents_by_status=status_counts,
    )

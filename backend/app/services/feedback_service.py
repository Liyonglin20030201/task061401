from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Feedback, Message
from app.schemas import FeedbackCreate, FeedbackStats
from app.core.exceptions import ConflictException, NotFoundException


async def create_feedback(data: FeedbackCreate, user_id: UUID, db: AsyncSession) -> Feedback:
    # Check message exists
    result = await db.execute(select(Message).where(Message.id == data.message_id))
    if not result.scalar_one_or_none():
        raise NotFoundException("Message not found")

    # Check duplicate
    existing = await db.execute(
        select(Feedback).where(
            Feedback.message_id == data.message_id,
            Feedback.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("Feedback already submitted for this message")

    feedback = Feedback(
        message_id=data.message_id,
        user_id=user_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(feedback)
    await db.flush()
    return feedback


async def get_feedback_stats(db: AsyncSession) -> FeedbackStats:
    total_result = await db.execute(select(func.count(Feedback.id)))
    total = total_result.scalar() or 0

    avg_result = await db.execute(select(func.avg(Feedback.rating)))
    avg_rating = float(avg_result.scalar() or 0)

    # Rating distribution
    distribution = {}
    for rating in range(1, 6):
        count_result = await db.execute(
            select(func.count(Feedback.id)).where(Feedback.rating == rating)
        )
        distribution[str(rating)] = count_result.scalar() or 0

    # Recent negative feedback (rating <= 2)
    negative_result = await db.execute(
        select(Feedback)
        .where(Feedback.rating <= 2)
        .order_by(Feedback.created_at.desc())
        .limit(10)
    )
    recent_negative = [
        {
            "id": str(f.id),
            "message_id": str(f.message_id),
            "rating": f.rating,
            "comment": f.comment,
            "created_at": f.created_at.isoformat(),
        }
        for f in negative_result.scalars().all()
    ]

    return FeedbackStats(
        total_feedback=total,
        average_rating=round(avg_rating, 2),
        rating_distribution=distribution,
        recent_negative=recent_negative,
    )

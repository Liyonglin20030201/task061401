from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, cast, Date, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Feedback, Conversation, QuestionCluster
from app.services.embedding_service import generate_embeddings


async def get_top_questions(
    db: AsyncSession,
    kb_id: Optional[UUID] = None,
    days: int = 30,
    limit: int = 20,
) -> list[dict]:
    filters = [QuestionCluster.last_asked_at >= datetime.utcnow() - timedelta(days=days)]
    if kb_id:
        filters.append(QuestionCluster.kb_id == kb_id)

    result = await db.execute(
        select(QuestionCluster)
        .where(*filters)
        .order_by(QuestionCluster.question_count.desc())
        .limit(limit)
    )
    clusters = result.scalars().all()
    return [
        {
            "representative_question": c.representative_question,
            "question_count": c.question_count,
            "avg_rating": c.avg_rating,
            "avg_confidence": c.avg_confidence,
            "last_asked_at": c.last_asked_at,
        }
        for c in clusters
    ]


async def get_satisfaction_trend(
    db: AsyncSession,
    kb_id: Optional[UUID] = None,
    days: int = 30,
) -> list[dict]:
    start_date = datetime.utcnow() - timedelta(days=days)

    query = (
        select(
            cast(Feedback.created_at, Date).label("date"),
            func.avg(cast(Feedback.rating, Float)).label("avg_rating"),
            func.count(Feedback.id).label("total"),
        )
        .where(Feedback.created_at >= start_date)
        .group_by(cast(Feedback.created_at, Date))
        .order_by(cast(Feedback.created_at, Date))
    )

    if kb_id:
        query = (
            query
            .join(Message, Message.id == Feedback.message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.kb_id == kb_id)
        )

    result = await db.execute(query)
    return [
        {
            "date": str(row.date),
            "avg_rating": round(float(row.avg_rating), 2),
            "total_feedback": row.total,
        }
        for row in result.fetchall()
    ]


async def get_accuracy_stats(
    db: AsyncSession,
    kb_id: Optional[UUID] = None,
    days: int = 30,
) -> dict:
    start_date = datetime.utcnow() - timedelta(days=days)

    filters = [
        Message.role == "assistant",
        Message.created_at >= start_date,
        Message.confidence_score.isnot(None),
    ]
    if kb_id:
        filters.append(
            Message.conversation_id.in_(
                select(Conversation.id).where(Conversation.kb_id == kb_id)
            )
        )

    total = (await db.execute(
        select(func.count(Message.id)).where(*filters)
    )).scalar() or 0

    high_conf = (await db.execute(
        select(func.count(Message.id)).where(*filters, Message.confidence_score >= 0.75)
    )).scalar() or 0

    low_conf = (await db.execute(
        select(func.count(Message.id)).where(*filters, Message.confidence_score < 0.75)
    )).scalar() or 0

    avg_conf = float((await db.execute(
        select(func.avg(Message.confidence_score)).where(*filters)
    )).scalar() or 0)

    time_result = await db.execute(
        select(
            cast(Message.created_at, Date).label("date"),
            func.avg(Message.confidence_score).label("avg_confidence"),
        )
        .where(*filters)
        .group_by(cast(Message.created_at, Date))
        .order_by(cast(Message.created_at, Date))
    )

    return {
        "total_questions": total,
        "high_confidence_count": high_conf,
        "low_confidence_count": low_conf,
        "avg_confidence": round(avg_conf, 4),
        "confidence_over_time": [
            {"date": str(row.date), "avg_confidence": round(float(row.avg_confidence), 4)}
            for row in time_result.fetchall()
        ],
    }


async def get_knowledge_gaps(
    db: AsyncSession,
    kb_id: Optional[UUID] = None,
    days: int = 30,
    limit: int = 20,
) -> list[dict]:
    start_date = datetime.utcnow() - timedelta(days=days)

    filters = [
        Message.role == "assistant",
        Message.created_at >= start_date,
    ]
    if kb_id:
        filters.append(
            Message.conversation_id.in_(
                select(Conversation.id).where(Conversation.kb_id == kb_id)
            )
        )

    gap_query = (
        select(
            Message.content,
            Message.confidence_score,
            Message.created_at,
            Feedback.rating,
        )
        .outerjoin(Feedback, Feedback.message_id == Message.id)
        .where(
            *filters,
            (Message.confidence_score < 0.75) | (Feedback.rating <= 2),
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(gap_query)
    rows = result.fetchall()

    return [
        {
            "question": row.content[:200],
            "confidence_score": row.confidence_score or 0.0,
            "avg_rating": float(row.rating) if row.rating else None,
            "occurrence_count": 1,
            "last_asked_at": row.created_at,
        }
        for row in rows
    ]


async def cluster_questions_batch(db: AsyncSession, kb_id: Optional[UUID] = None):
    start_date = datetime.utcnow() - timedelta(days=7)

    filters = [Message.role == "user", Message.created_at >= start_date]
    if kb_id:
        filters.append(
            Message.conversation_id.in_(
                select(Conversation.id).where(Conversation.kb_id == kb_id)
            )
        )

    result = await db.execute(
        select(Message.content, Message.created_at)
        .where(*filters)
        .order_by(Message.created_at.desc())
        .limit(500)
    )
    messages = result.fetchall()

    if not messages:
        return

    texts = [m.content for m in messages]
    embeddings = await generate_embeddings(texts)

    # Greedy nearest-neighbor clustering
    clusters = []
    used = set()
    threshold = 0.85

    for i in range(len(embeddings)):
        if i in used:
            continue
        cluster = [i]
        used.add(i)
        emb_i = embeddings[i]
        norm_i = sum(a * a for a in emb_i) ** 0.5
        for j in range(i + 1, len(embeddings)):
            if j in used:
                continue
            emb_j = embeddings[j]
            dot = sum(a * b for a, b in zip(emb_i, emb_j))
            norm_j = sum(a * a for a in emb_j) ** 0.5
            sim = dot / (norm_i * norm_j + 1e-8)
            if sim >= threshold:
                cluster.append(j)
                used.add(j)
        if len(cluster) >= 2:
            clusters.append(cluster)

    for cluster_indices in clusters:
        representative = texts[cluster_indices[0]]
        centroid = [
            sum(embeddings[idx][d] for idx in cluster_indices) / len(cluster_indices)
            for d in range(len(embeddings[0]))
        ]

        qc = QuestionCluster(
            kb_id=kb_id,
            representative_question=representative[:500],
            question_count=len(cluster_indices),
            centroid_embedding=centroid,
            last_asked_at=messages[cluster_indices[0]].created_at,
        )
        db.add(qc)

    await db.commit()

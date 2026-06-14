from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentEmbedding, DocumentChunk, KnowledgeBase, Message, Conversation
from app.services.embedding_service import generate_single_embedding
from app.core.cache import TTLCache

recommendation_cache = TTLCache(maxsize=256, ttl=300, jitter=0.2)


async def compute_document_embedding(document_id: UUID, db: AsyncSession) -> list[float] | None:
    result = await db.execute(
        select(DocumentChunk.embedding)
        .where(DocumentChunk.document_id == document_id)
    )
    embeddings = [row[0] for row in result.fetchall() if row[0] is not None]

    if not embeddings:
        return None

    dim = len(embeddings[0])
    avg = [sum(emb[i] for emb in embeddings) / len(embeddings) for i in range(dim)]
    return avg


async def ensure_document_embedding(document_id: UUID, db: AsyncSession) -> DocumentEmbedding | None:
    result = await db.execute(
        select(DocumentEmbedding).where(DocumentEmbedding.document_id == document_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    avg_embedding = await compute_document_embedding(document_id, db)
    if avg_embedding is None:
        return None

    doc_emb = DocumentEmbedding(document_id=document_id, embedding=avg_embedding)
    db.add(doc_emb)
    await db.flush()
    return doc_emb


async def get_document_recommendations(
    document_id: UUID,
    db: AsyncSession,
    user_accessible_kb_ids: list[UUID],
    top_k: int = 5,
) -> list[dict]:
    cache_key = f"doc_rec:{document_id}"
    cached = recommendation_cache.get(cache_key)
    if cached is not None:
        return cached

    doc_emb = await ensure_document_embedding(document_id, db)
    if doc_emb is None:
        return []

    embedding_str = "[" + ",".join(str(x) for x in doc_emb.embedding) + "]"
    kb_ids_str = [str(k) for k in user_accessible_kb_ids]

    sql = text("""
        SELECT de.document_id, d.title, d.kb_id, kb.name as kb_name,
               1 - (de.embedding <=> :embedding::vector) as similarity
        FROM document_embeddings de
        JOIN documents d ON d.id = de.document_id
        JOIN knowledge_bases kb ON kb.id = d.kb_id
        WHERE de.document_id != :doc_id
          AND d.status = 'ready'
          AND d.kb_id = ANY(:kb_ids::uuid[])
        ORDER BY de.embedding <=> :embedding::vector
        LIMIT :top_k
    """)

    result = await db.execute(sql, {
        "embedding": embedding_str,
        "doc_id": str(document_id),
        "kb_ids": kb_ids_str,
        "top_k": top_k,
    })

    recommendations = [
        {
            "document_id": str(row.document_id),
            "title": row.title,
            "similarity": round(float(row.similarity), 4),
            "kb_name": row.kb_name,
        }
        for row in result.fetchall()
    ]
    recommendation_cache.set(cache_key, recommendations)
    return recommendations


async def get_conversation_recommendations(
    conversation_id: UUID,
    db: AsyncSession,
    user_accessible_kb_ids: list[UUID],
    top_k: int = 5,
) -> list[dict]:
    result = await db.execute(
        select(Message.content)
        .where(Message.conversation_id == conversation_id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .limit(5)
    )
    messages = [row[0] for row in result.fetchall()]

    if not messages:
        return []

    combined = " ".join(messages[:3])[:1000]
    topic_embedding = await generate_single_embedding(combined)

    embedding_str = "[" + ",".join(str(x) for x in topic_embedding) + "]"
    kb_ids_str = [str(k) for k in user_accessible_kb_ids]

    sql = text("""
        SELECT de.document_id, d.title, d.kb_id, kb.name as kb_name,
               1 - (de.embedding <=> :embedding::vector) as similarity
        FROM document_embeddings de
        JOIN documents d ON d.id = de.document_id
        JOIN knowledge_bases kb ON kb.id = d.kb_id
        WHERE d.status = 'ready'
          AND d.kb_id = ANY(:kb_ids::uuid[])
        ORDER BY de.embedding <=> :embedding::vector
        LIMIT :top_k
    """)

    result = await db.execute(sql, {
        "embedding": embedding_str,
        "kb_ids": kb_ids_str,
        "top_k": top_k,
    })

    return [
        {
            "document_id": str(row.document_id),
            "title": row.title,
            "similarity": round(float(row.similarity), 4),
            "kb_name": row.kb_name,
        }
        for row in result.fetchall()
    ]

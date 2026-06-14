import json
from typing import AsyncGenerator, Optional
from uuid import UUID

import openai
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    DocumentChunk, Document, Conversation, Message,
    KnowledgeBase, KBAccess, User, AccessLevel, KBPermission
)
from app.services.embedding_service import generate_single_embedding
from app.core.exceptions import ForbiddenException, NotFoundException

settings = get_settings()

SYSTEM_PROMPT = """You are a customer service knowledge base assistant. You MUST follow these rules strictly:

1. Answer ONLY based on the provided context. Do NOT use any external knowledge.
2. If the context doesn't contain enough information to answer the question, respond with: "抱歉，知识库中未找到相关信息，无法回答您的问题。"
3. Always cite your sources using [1], [2], etc. format, corresponding to the numbered context sections.
4. Be concise and accurate. Do not elaborate beyond what the context supports.
5. If a question is ambiguous, ask for clarification rather than guessing.
6. Respond in the same language as the user's question."""


async def check_kb_access(user: User, kb_id: UUID, db: AsyncSession) -> bool:
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise NotFoundException("Knowledge base not found")

    if kb.access_level == AccessLevel.public:
        return True
    if kb.access_level == AccessLevel.internal and user:
        return True
    if kb.access_level == AccessLevel.restricted:
        if user.role.value == "admin":
            return True
        if kb.owner_id == user.id:
            return True
        access = await db.execute(
            select(KBAccess).where(
                KBAccess.kb_id == kb_id,
                KBAccess.user_id == user.id,
            )
        )
        if access.scalar_one_or_none():
            return True

    raise ForbiddenException("You do not have access to this knowledge base")


async def vector_search(
    query_embedding: list[float],
    kb_id: UUID,
    db: AsyncSession,
    top_k: int = None,
) -> list[dict]:
    if top_k is None:
        top_k = settings.max_retrieval_count

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = text("""
        SELECT dc.id, dc.content, dc.metadata, dc.chunk_index,
               d.title as doc_title, d.id as doc_id,
               1 - (dc.embedding <=> :embedding::vector) as similarity
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE d.kb_id = :kb_id AND d.status = 'ready'
        ORDER BY dc.embedding <=> :embedding::vector
        LIMIT :top_k
    """)

    result = await db.execute(sql, {
        "embedding": embedding_str,
        "kb_id": str(kb_id),
        "top_k": top_k,
    })

    rows = result.fetchall()
    return [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "metadata": row.metadata or {},
            "chunk_index": row.chunk_index,
            "doc_title": row.doc_title,
            "doc_id": str(row.doc_id),
            "similarity": float(row.similarity),
        }
        for row in rows
    ]


def build_rag_prompt(question: str, context_chunks: list[dict]) -> list[dict]:
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        source_info = f"[Source: {chunk['doc_title']}"
        if chunk.get("metadata", {}).get("page"):
            source_info += f", Page {chunk['metadata']['page']}"
        source_info += "]"
        context_parts.append(f"[{i}] {source_info}\n{chunk['content']}")

    context_text = "\n\n---\n\n".join(context_parts)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context_text}\n\n---\n\nQuestion: {question}"},
    ]
    return messages


async def stream_chat_response(
    question: str,
    context_chunks: list[dict],
) -> AsyncGenerator[str, None]:
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    messages = build_rag_prompt(question, context_chunks)

    stream = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        stream=True,
        temperature=0.1,
        max_tokens=2048,
    )

    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def get_or_create_conversation(
    user_id: UUID,
    kb_id: UUID,
    conversation_id: Optional[UUID],
    db: AsyncSession,
) -> Conversation:
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(user_id=user_id, kb_id=kb_id)
    db.add(conv)
    await db.flush()
    return conv


async def save_message(
    conversation_id: UUID,
    role: str,
    content: str,
    citations: list = None,
    db: AsyncSession = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations or [],
    )
    db.add(msg)
    await db.flush()
    return msg

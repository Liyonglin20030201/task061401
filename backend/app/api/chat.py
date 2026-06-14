import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Conversation, Message
from app.schemas import ChatRequest, ConversationOut, MessageOut, CorrectionRequest
from app.services.chat_service import (
    check_kb_access, vector_search, stream_chat_response,
    get_or_create_conversation, save_message, load_conversation_history,
)
from app.services.embedding_service import generate_single_embedding
from app.services.sensitive_filter import sensitive_filter
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException, AppException
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/")
async def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check access
    await check_kb_access(user, data.kb_id, db)

    # Sensitive word check on input
    has_sensitive, words = sensitive_filter.contains_sensitive(data.message)
    if has_sensitive:
        raise AppException(f"Your message contains restricted content and cannot be processed.")

    # Generate query embedding
    query_embedding = await generate_single_embedding(data.message)

    # Vector search
    results = await vector_search(query_embedding, data.kb_id, db, user_department=user.department)

    # Check confidence threshold
    if not results or results[0]["similarity"] < settings.similarity_threshold:
        # Low confidence — return disclaimer
        conv = await get_or_create_conversation(user.id, data.kb_id, data.conversation_id, db)
        await save_message(conv.id, "user", data.message, db=db)
        no_info_msg = "抱歉，知识库中未找到与您问题相关的信息，无法为您提供准确回答。"
        msg = await save_message(conv.id, "assistant", no_info_msg, citations=[], db=db)
        msg.confidence_score = results[0]["similarity"] if results else 0.0
        await db.commit()
        return {"message": no_info_msg, "citations": [], "conversation_id": str(conv.id)}

    # Build citations
    citations = [
        {
            "chunk_id": r["chunk_id"],
            "score": round(r["similarity"], 4),
            "snippet": r["content"][:200],
            "document_title": r["doc_title"],
            "page_info": r["metadata"].get("page"),
        }
        for r in results
    ]

    # Get or create conversation
    conv = await get_or_create_conversation(user.id, data.kb_id, data.conversation_id, db)

    # Load conversation history BEFORE saving current message,
    # otherwise the current question leaks into history context
    conversation_history = []
    if data.conversation_id:
        conversation_history = await load_conversation_history(conv.id, db)

    await save_message(conv.id, "user", data.message, db=db)

    # Update conversation title from first message
    if conv.title == "New Conversation":
        conv.title = data.message[:50]

    # Best confidence score for analytics
    best_confidence = results[0]["similarity"] if results else None

    # Stream response via SSE
    async def event_stream():
        full_response = ""
        async for token in stream_chat_response(data.message, results, conversation_history):
            # Filter output sensitive words
            masked = sensitive_filter.mask_sensitive(token)
            full_response += masked
            yield f"data: {json.dumps({'token': masked})}\n\n"

        # Save complete message with confidence score
        msg = await save_message(conv.id, "assistant", full_response, citations=citations, db=db)
        msg.confidence_score = best_confidence
        await db.commit()

        # Send final event with metadata
        yield f"data: {json.dumps({'done': True, 'citations': citations, 'conversation_id': str(conv.id)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/conversations/{conv_id}", response_model=list[MessageOut])
async def get_conversation_messages(
    conv_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user.id
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundException("Conversation not found")

    messages = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    )
    return messages.scalars().all()


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user.id
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundException("Conversation not found")
    await db.delete(conv)


@router.get("/recommendations")
async def chat_recommendations(
    conversation_id: UUID = Query(...),
    top_k: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundException("Conversation not found")

    from app.api.documents import get_user_accessible_kb_ids
    accessible_kbs = await get_user_accessible_kb_ids(user, db)

    from app.services.recommendation_service import get_conversation_recommendations
    return await get_conversation_recommendations(conversation_id, db, accessible_kbs, top_k)


@router.put("/messages/{msg_id}/correct", response_model=MessageOut)
async def correct_message(
    msg_id: UUID,
    data: CorrectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Message).where(Message.id == msg_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise NotFoundException("Message not found")

    msg.is_corrected = True
    msg.corrected_content = data.corrected_content
    await db.flush()
    return msg

from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocStatus
from app.services.document_service import parse_document
from app.services.chunking_service import smart_chunk
from app.services.embedding_service import generate_embeddings
from app.core.cache import query_cache
from app.database import async_session_factory


async def process_document(document_id: UUID):
    async with async_session_factory() as db:
        # Acquire row lock — skip if another task already holds it
        result = await db.execute(
            select(Document)
            .where(Document.id == document_id)
            .with_for_update(skip_locked=True)
        )
        doc = result.scalar_one_or_none()
        if not doc or doc.status == DocStatus.processing:
            return

        doc.status = DocStatus.processing
        await db.commit()

    # Processing outside the lock session to avoid long-held locks
    try:
        sections = parse_document(doc.file_path, doc.file_type)
        chunks = smart_chunk(sections)

        if not chunks:
            async with async_session_factory() as db:
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(status=DocStatus.error)
                )
                await db.commit()
            return

        texts = [c["content"] for c in chunks]
        embeddings = await generate_embeddings(texts)

        # Atomic swap: bulk delete old chunks + insert new in one transaction
        async with async_session_factory() as db:
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
            db.add_all([
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=i,
                    content=c["content"],
                    embedding=emb,
                    metadata_=c.get("metadata", {}),
                    token_count=c["token_count"],
                )
                for i, (c, emb) in enumerate(zip(chunks, embeddings))
            ])
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocStatus.ready)
            )
            await db.commit()

        # Invalidate search cache after successful re-index
        query_cache.clear()

    except Exception:
        # Use a fresh session to mark error — avoids poisoned-session issues
        async with async_session_factory() as err_db:
            await err_db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocStatus.error)
            )
            await err_db.commit()
        raise

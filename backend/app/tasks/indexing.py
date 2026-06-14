from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentEmbedding, DocStatus
from app.services.document_service import parse_document
from app.services.chunking_service import smart_chunk
from app.services.embedding_service import generate_embeddings
from app.services.recommendation_service import compute_document_embedding
from app.core.cache import query_cache
from app.database import async_session_factory


async def process_document(document_id: UUID):
    # Phase 1: acquire row lock and mark processing
    async with async_session_factory() as db:
        result = await db.execute(
            select(Document)
            .where(Document.id == document_id)
            .with_for_update(nowait=False)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return
        if doc.status == DocStatus.processing:
            return

        doc.status = DocStatus.processing
        # Delete old vectors NOW while we hold the lock — guarantees no stale reads
        await db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await db.commit()

    # Phase 2: parse, chunk, embed (no lock held — heavy I/O)
    try:
        sections = parse_document(doc.file_path, doc.file_type)
        if not sections:
            raise ValueError("Document parsed to empty content")

        chunks = smart_chunk(sections)
        if not chunks:
            raise ValueError("Chunking produced no output")

        texts = [c["content"] for c in chunks]
        embeddings = await generate_embeddings(texts)

        # Phase 3: insert new vectors + mark ready (single transaction)
        async with async_session_factory() as db:
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

        # Phase 4: compute document-level embedding for recommendations
        async with async_session_factory() as db:
            avg_emb = await compute_document_embedding(document_id, db)
            if avg_emb:
                existing = await db.execute(
                    select(DocumentEmbedding).where(DocumentEmbedding.document_id == document_id)
                )
                doc_emb = existing.scalar_one_or_none()
                if doc_emb:
                    doc_emb.embedding = avg_emb
                else:
                    db.add(DocumentEmbedding(document_id=document_id, embedding=avg_emb))
                await db.commit()

        query_cache.clear()

    except Exception:
        async with async_session_factory() as err_db:
            await err_db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocStatus.error)
            )
            await err_db.commit()
        raise

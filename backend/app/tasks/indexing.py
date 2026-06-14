from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocStatus
from app.services.document_service import parse_document, delete_document_chunks
from app.services.chunking_service import smart_chunk
from app.services.embedding_service import generate_embeddings
from app.database import async_session_factory


async def process_document(document_id: UUID):
    async with async_session_factory() as db:
        try:
            result = await db.execute(select(Document).where(Document.id == document_id))
            doc = result.scalar_one_or_none()
            if not doc:
                return

            doc.status = DocStatus.processing
            await db.commit()

            # Parse document
            sections = parse_document(doc.file_path, doc.file_type)

            # Chunk with hybrid strategy
            chunks = smart_chunk(sections)

            if not chunks:
                doc.status = DocStatus.error
                await db.commit()
                return

            # Generate embeddings in batch
            texts = [c["content"] for c in chunks]
            embeddings = await generate_embeddings(texts)

            # Delete old chunks (for re-indexing)
            await delete_document_chunks(document_id, db)

            # Store new chunks
            for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
                chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_index=i,
                    content=chunk_data["content"],
                    embedding=embedding,
                    metadata_=chunk_data.get("metadata", {}),
                    token_count=chunk_data["token_count"],
                )
                db.add(chunk)

            doc.status = DocStatus.ready
            await db.commit()

        except Exception as e:
            doc.status = DocStatus.error
            await db.commit()
            raise

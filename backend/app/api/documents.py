from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, BackgroundTasks
from sqlalchemy import select, cast, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Document, DocumentChunk, KnowledgeBase, KBAccess,
    User, UserRole, DocStatus, AccessLevel, KBPermission
)
from app.schemas import (
    KBCreate, KBUpdate, KBOut, KBAccessGrant,
    DocumentOut, ChunkOut
)
from app.core.cache import kb_access_cache
from app.services.document_service import save_uploaded_file, compute_file_hash, get_document_or_404
from app.services.chat_service import check_kb_access
from app.tasks.indexing import process_document
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import NotFoundException, ForbiddenException

router = APIRouter(prefix="/api", tags=["documents"])


# ===== Knowledge Base Routes =====

@router.get("/kb", response_model=list[KBOut])
async def list_knowledge_bases(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == UserRole.admin:
        result = await db.execute(select(KnowledgeBase))
    else:
        dept_filter = or_(
            KnowledgeBase.departments == cast([], JSONB),
            KnowledgeBase.departments.contains(cast([user.department], JSONB))
        ) if user.department else (KnowledgeBase.departments == cast([], JSONB))

        result = await db.execute(
            select(KnowledgeBase).where(
                dept_filter,
                (KnowledgeBase.access_level == AccessLevel.public) |
                (KnowledgeBase.access_level == AccessLevel.internal) |
                (KnowledgeBase.owner_id == user.id) |
                (KnowledgeBase.id.in_(
                    select(KBAccess.kb_id).where(KBAccess.user_id == user.id)
                ))
            )
        )
    return result.scalars().all()


@router.post("/kb", response_model=KBOut, status_code=201)
async def create_knowledge_base(
    data: KBCreate,
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    kb = KnowledgeBase(
        name=data.name,
        description=data.description,
        access_level=AccessLevel(data.access_level),
        departments=data.departments,
        owner_id=user.id,
    )
    db.add(kb)
    await db.flush()
    return kb


@router.put("/kb/{kb_id}", response_model=KBOut)
async def update_knowledge_base(
    kb_id: UUID,
    data: KBUpdate,
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise NotFoundException("Knowledge base not found")
    if kb.owner_id != user.id and user.role != UserRole.admin:
        raise ForbiddenException()

    if data.name:
        kb.name = data.name
    if data.description is not None:
        kb.description = data.description
    if data.access_level:
        kb.access_level = AccessLevel(data.access_level)
    if data.departments is not None:
        kb.departments = data.departments
    await db.flush()
    return kb


@router.delete("/kb/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: UUID,
    user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise NotFoundException("Knowledge base not found")
    await db.delete(kb)


@router.post("/kb/{kb_id}/access", status_code=201)
async def grant_kb_access(
    kb_id: UUID,
    data: KBAccessGrant,
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    access = KBAccess(
        kb_id=kb_id,
        user_id=data.user_id,
        permission=KBPermission(data.permission),
    )
    db.add(access)
    await db.flush()
    kb_access_cache.invalidate(f"{data.user_id}:{kb_id}")
    return {"status": "granted"}


@router.delete("/kb/{kb_id}/access/{user_id}", status_code=204)
async def revoke_kb_access(
    kb_id: UUID,
    user_id: UUID,
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KBAccess).where(KBAccess.kb_id == kb_id, KBAccess.user_id == user_id)
    )
    access = result.scalar_one_or_none()
    if access:
        await db.delete(access)
        kb_access_cache.invalidate(f"{user_id}:{kb_id}")


# ===== Document Routes =====

@router.post("/documents/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    kb_id: UUID = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    # Validate file type
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "docx", "md"):
        raise ForbiddenException("Unsupported file type. Use PDF, DOCX, or MD.")

    content = await file.read()
    file_path = await save_uploaded_file(content, file.filename, kb_id)
    file_hash = compute_file_hash(file_path)

    doc = Document(
        kb_id=kb_id,
        title=title,
        file_path=file_path,
        file_type=ext,
        file_hash=file_hash,
        status=DocStatus.pending,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.flush()

    background_tasks.add_task(process_document, doc.id)
    return doc


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    kb_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await check_kb_access(user, kb_id, db)
    result = await db.execute(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/documents/{doc_id}/status")
async def get_document_status(
    doc_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await get_document_or_404(doc_id, db)
    return {"status": doc.status.value, "version": doc.version}


@router.put("/documents/{doc_id}", response_model=DocumentOut)
async def update_document(
    doc_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    doc = await get_document_or_404(doc_id, db)

    content = await file.read()
    file_path = await save_uploaded_file(content, file.filename, doc.kb_id)
    new_hash = compute_file_hash(file_path)

    if new_hash != doc.file_hash:
        doc.file_path = file_path
        doc.file_hash = new_hash
        doc.version += 1
        doc.status = DocStatus.pending
        await db.commit()
        background_tasks.add_task(process_document, doc.id)

    return doc


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: UUID,
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
    db: AsyncSession = Depends(get_db),
):
    doc = await get_document_or_404(doc_id, db)
    await db.delete(doc)


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(
    doc_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return result.scalars().all()

"""Evidence API endpoints for object storage."""

from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import re
import tempfile
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import verify_project_access
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.evidence import Evidence
from app.models.expense import Expense
from app.models.user import User

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tiff", ".bmp"}
MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB


def validate_magic_bytes(header: bytes, ext: str) -> bool:
    """Validate initial file bytes against known magic signatures for allowed extensions."""
    if not header or len(header) < 4:
        return False
    if ext == ".pdf":
        return header.startswith(b"%PDF")
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if ext == ".webp":
        return header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP"
    if ext == ".tiff":
        return header.startswith(b"II*\x00") or header.startswith(b"MM\x00*")
    if ext == ".bmp":
        return header.startswith(b"BM")
    if ext == ".heic":
        return len(header) >= 12 and b"ftyp" in header[:12]
    return True
from app.schemas.evidence import (
    EvidenceListResponse,
    EvidenceResponse,
    EvidenceUploadResponse,
    PresignedUrlRequest,
    PresignedUrlResponse,
)
from app.services.storage import create_storage_service

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.post("/upload", response_model=EvidenceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    expense_id: UUID,
    file: UploadFile = File(...),
    metadata: dict[str, Any] | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceUploadResponse:
    """Upload evidence file for an expense with magic byte inspection and project authorization."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    # Sanitize filename and validate extension against path traversal and disallowed types
    raw_filename = Path(file.filename).name
    ext = Path(raw_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    expense = await db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    await verify_project_access(db, current_user, expense.project_id)

    clean_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(raw_filename).stem)[:80]
    safe_filename = f"{clean_stem}_{uuid4().hex[:8]}{ext}"
    object_name = f"expenses/{expense_id}/{safe_filename}"

    # Enforce bounded memory streaming with maximum upload size & magic byte check
    hasher = hashlib.sha256()
    total_size = 0
    chunk_size = 1024 * 1024  # 1 MB
    is_first = True

    with tempfile.SpooledTemporaryFile(max_size=512 * 1024) as temp_file:
        while chunk := await file.read(chunk_size):
            if is_first:
                if not validate_magic_bytes(chunk, ext):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File content does not match allowed signature for '{ext}'",
                    )
                is_first = False

            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File size exceeds maximum allowed limit of 25MB",
                )
            hasher.update(chunk)
            temp_file.write(chunk)

        if total_size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

        checksum = hasher.hexdigest()
        temp_file.seek(0)

        storage = create_storage_service()
        object_name, checksum = storage.upload_stream(
            object_name=object_name,
            stream=temp_file,
            length=total_size,
            checksum=checksum,
            content_type=file.content_type,
            metadata=metadata,
        )

        evidence = Evidence(
            expense_id=expense_id,
            object_name=object_name,
            file_name=safe_filename,
            content_type=file.content_type or "application/octet-stream",
            size=total_size,
            checksum=checksum,
            file_metadata=metadata,
        )
        db.add(evidence)
        await db.flush()
        await db.refresh(evidence)

    presigned_url = storage.generate_presigned_url(object_name, expires=timedelta(hours=1))
    expires_at = datetime.utcnow() + timedelta(hours=1)

    return EvidenceUploadResponse(
        object_name=object_name,
        checksum=checksum,
        size=total_size,
        content_type=file.content_type or "application/octet-stream",
        presigned_url=presigned_url,
        expires_at=expires_at,
    )


@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceResponse:
    """Get evidence by ID with project authorization."""
    evidence = await db.get(Evidence, evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    expense = await db.get(Expense, evidence.expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await verify_project_access(db, current_user, expense.project_id)

    return EvidenceResponse.model_validate(evidence)


@router.get("/expense/{expense_id}", response_model=EvidenceListResponse)
async def list_evidence_by_expense(
    expense_id: UUID,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceListResponse:
    """List evidence files for an expense with project authorization."""
    expense = await db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    await verify_project_access(db, current_user, expense.project_id)

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Evidence)
        .where(Evidence.expense_id == expense_id)
        .offset(offset)
        .limit(page_size)
    )
    items = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Evidence.id)).where(Evidence.expense_id == expense_id)
    )
    total = count_result.scalar_one()

    return EvidenceListResponse(
        items=[EvidenceResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    request: PresignedUrlRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PresignedUrlResponse:
    """Generate presigned URL for evidence access with DB verification and project authorization."""
    result = await db.execute(
        select(Evidence).where(Evidence.object_name == request.object_name)
    )
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found or access denied",
        )

    expense = await db.get(Expense, evidence.expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await verify_project_access(db, current_user, expense.project_id)

    storage = create_storage_service()
    if not storage.file_exists(request.object_name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in storage")

    # Limit maximum expiration to 1 hour (3600s) to prevent indefinite exposure
    expires_in = min(max(request.expires_in_seconds, 60), 3600)
    expires = timedelta(seconds=expires_in)
    url = storage.generate_presigned_url(request.object_name, expires=expires)

    return PresignedUrlResponse(
        url=url,
        expires_at=datetime.utcnow() + expires,
        method=request.method,
    )


@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence(
    evidence_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete evidence file with project authorization."""
    evidence = await db.get(Evidence, evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    expense = await db.get(Expense, evidence.expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await verify_project_access(db, current_user, expense.project_id)

    storage = create_storage_service()
    storage.delete_file(evidence.object_name)

    await db.delete(evidence)
    await db.commit()

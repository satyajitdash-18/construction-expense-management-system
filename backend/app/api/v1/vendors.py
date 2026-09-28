from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.vendor import Vendor
from app.schemas.vendor import (
    VendorCreate,
    VendorListResponse,
    VendorResponse,
    VendorUpdate,
)

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=VendorListResponse)
async def list_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=100),
    offset: int | None = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> VendorListResponse:
    # Handle either page/page_size or limit/offset
    effective_limit = limit if limit is not None else page_size
    effective_offset = offset if offset is not None else (page - 1) * page_size

    query = select(Vendor)
    count_query = select(func.count()).select_from(Vendor)

    if search:
        search_filter = or_(
            Vendor.name.ilike(f"%{search}%"),
            Vendor.gstin.ilike(f"%{search}%"),
            Vendor.phone.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Vendor.name.asc()).offset(effective_offset).limit(effective_limit)
    result = await db.execute(query)
    vendors = result.scalars().all()

    return VendorListResponse(
        items=[VendorResponse.model_validate(v) for v in vendors],
        total=total,
        page=page,
        page_size=effective_limit,
        limit=effective_limit,
        offset=effective_offset,
    )


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> VendorResponse:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return VendorResponse.model_validate(vendor)


@router.post("", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    request: VendorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> VendorResponse:
    vendor = Vendor(
        name=request.name,
        gstin=request.gstin,
        phone=request.phone,
        notes=request.notes,
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return VendorResponse.model_validate(vendor)


@router.patch("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: UUID,
    request: VendorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> VendorResponse:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    if request.name is not None:
        vendor.name = request.name
    if request.gstin is not None:
        vendor.gstin = request.gstin
    if request.phone is not None:
        vendor.phone = request.phone
    if request.notes is not None:
        vendor.notes = request.notes

    await db.commit()
    await db.refresh(vendor)
    return VendorResponse.model_validate(vendor)


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor(
    vendor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> None:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    await db.delete(vendor)
    await db.commit()

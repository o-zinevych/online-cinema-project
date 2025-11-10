from typing import TypeVar, Type

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Select, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

TSchema = TypeVar("TSchema", bound=BaseModel)


def count_offset(page: int, per_page: int) -> int:
    """Counts the offset for pagination based on current page and per_page."""
    return (page - 1) * per_page


def count_total_pages(total_items: int, per_page: int) -> int:
    """Counts the total pages number for pagination based on items total and per_page."""
    return (total_items + per_page - 1) // per_page


async def count_total_items(stmt: Select, db: AsyncSession = Depends(get_db)) -> int:
    """Counts the total amount of items."""
    count_stmt = select(func.count()).select_from(stmt.alias())
    count_result = await db.execute(count_stmt)
    total_items = count_result.scalar() or 0
    return total_items


async def apply_limit_offset_to_item_list(
    stmt: Select,
    page: int,
    per_page: int,
    error_to_raise: HTTPException,
    list_item_schema: Type[TSchema],
    db: AsyncSession = Depends(get_db),
):
    """
    Applies the given limit and offset to the statement, executes it
    and returns the list of items.
    """
    offset = count_offset(page, per_page)
    stmt = stmt.limit(per_page).offset(offset)
    result = await db.execute(stmt)
    items = result.scalars().all()
    if not items:
        raise error_to_raise
    item_list = [list_item_schema.model_validate(item) for item in items]
    return item_list

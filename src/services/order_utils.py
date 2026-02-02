from decimal import Decimal
from typing import Sequence

from fastapi import Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from database import get_db
from database.models import Order, OrderItem, Movie
from schemas.orders import AdminOrderFilterParams

cancelled_order_exception = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="This order has already been cancelled.",
)
paid_order_exception = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="To cancel a paid order, please, submit a refund request.",
)
no_orders_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="No orders found."
)
order_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Order not found."
)
order_not_pending_exception = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="The order has already been paid for or canceled.",
)


async def has_user_order_statuses_for_movie(
    user_id: int,
    movie_id: int,
    statuses: list[str],
    db: AsyncSession = Depends(get_db),
) -> bool:
    """
    Checks if the user has orders with the specified statuses.

    Args:
        user_id (int): The ID of the current user.
        movie_id (int): The ID of the movie to be purchased.
        statuses (list[str]): The statuses of the movie order to check for.
        db (AsyncSession): Asynchronous database session.

    Returns:
        bool: True if the user has an order with the specified statuses.
    """
    stmt = (
        select(Order.id)
        .join(OrderItem, Order.id == OrderItem.order_id)
        .where(
            and_(
                Order.user_id == user_id,
                OrderItem.movie_id == movie_id,
                Order.status.in_(statuses),
            )
        )
        .limit(1)
    )

    result = await db.execute(stmt)
    return result.first() is not None


async def get_order_by_id(order_id: int, db: AsyncSession = Depends(get_db)) -> Order:
    """Retrieves an order by the specified ID."""
    stmt = (
        select(Order)
        .options(selectinload(Order.order_items))
        .where(Order.id == order_id)
    )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    return order


def get_total_price_of_ordered_movies(movies: Sequence[Movie]) -> Decimal:
    """Calculates the total price of the given movies."""
    total = sum(movie.price for movie in movies if movie.price)
    return Decimal(total)


def add_filters_to_order_list_page_links(
    base_url: str, filter_params: AdminOrderFilterParams
) -> str:
    """Adds provided filters to orders list page links."""
    return (
        f"{base_url}"
        + (f"&user_id={filter_params.user_id}" if filter_params.user_id else "")
        + (f"&date={filter_params.date}" if filter_params.date else "")
        + (f"&status={filter_params.status}" if filter_params.status else "")
    )

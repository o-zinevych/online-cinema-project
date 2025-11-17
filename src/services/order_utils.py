from decimal import Decimal
from typing import Sequence

from fastapi import Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from database import get_db
from database.models import Order, OrderItem, Movie


no_orders_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="No orders found."
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


def get_total_price_of_ordered_movies(movies: Sequence[Movie]) -> Decimal:
    """Calculates the total price of the given movies."""
    total = sum(movie.price for movie in movies if movie.price)
    return Decimal(total)

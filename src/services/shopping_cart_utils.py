from typing import Sequence

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from database import get_db
from database.models import Cart, CartItem, Movie
from schemas.movies import MovieCartItemSchema


async def get_or_create_cart_by_user_id(
    user_id: int, db: AsyncSession = Depends(get_db)
) -> Cart:
    """
    Retrieves the given user's cart or creates on if none found.

    Args:
        user_id (int): The user's ID.
        db (AsyncSession): Asynchronous database session.

    Returns:
        Cart: The specified user's cart.

    Raises:
        HTTPException:
            - 500 if an error occurred during cart creation.
    """
    stmt = (
        select(Cart)
        .options(selectinload(Cart.cart_items))
        .where(Cart.user_id == user_id)
    )
    result = await db.execute(stmt)
    cart = result.scalar_one_or_none()
    if not cart:
        try:
            cart = Cart(user_id=user_id)
            db.add(cart)
            await db.flush()
        except SQLAlchemyError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred when creating a shopping cart.",
            )
    return cart


async def get_cart_item_by_id(
    cart_item_id: int, db: AsyncSession = Depends(get_db)
) -> CartItem:
    """Retrieves the specified cart item or raises 404 if not found."""
    stmt = select(CartItem).where(CartItem.id == cart_item_id)
    result = await db.execute(stmt)
    cart_item = result.scalar_one_or_none()
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found."
        )
    return cart_item


async def get_cart_item_movie_ids(
    cart_id: int, db: AsyncSession = Depends(get_db)
) -> list[int]:
    """Lists IDs of all cart item movies."""
    stmt = select(CartItem.movie_id).where(CartItem.cart_id == cart_id)
    result = await db.execute(stmt)
    return [movie_id for movie_id in result.scalars()]


async def get_movies_in_cart(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> Sequence[Movie]:
    """
    Retrieves all the movies in the given user's cart.

    Args:
        user_id (int): The user's ID.
        db (AsyncSession): Asynchronous database session.

    Returns:
        list[MovieCartItemSchema]: A list of all the movies in the shopping cart.
    """
    cart = await get_or_create_cart_by_user_id(user_id=user_id, db=db)

    stmt = (
        select(Movie)
        .join(CartItem, CartItem.movie_id == Movie.id)
        .where(CartItem.cart_id == cart.id)
        .options(selectinload(Movie.genres))
    )
    result = await db.execute(stmt)
    movies = result.scalars().unique().all()
    return movies

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from database import get_db
from database.models import Cart, CartItem, Movie
from database.models.accounts import User
from database.models.orders import OrderStatusEnum
from schemas.common import MessageResponseSchema
from schemas.movies import MovieCartItemSchema
from schemas.shopping_carts import CartItemDetail
from services.account_utils import get_current_user, require_admin
from services.movie_utils import get_movie_by_id_stmt, movie_not_found_exception
from services.order_utils import has_user_order_statuses_for_movie
from services.shopping_cart_utils import (
    get_or_create_cart_by_user_id,
    get_movies_in_cart,
    get_cart_item_by_id,
)

router = APIRouter()


@router.get(
    "/",
    response_model=MessageResponseSchema | list[MovieCartItemSchema],
    summary="Get Shopping Cart Movie List",
    description="Retrieves a list of all the movies in the shopping cart.",
    status_code=status.HTTP_200_OK,
)
async def get_shopping_cart_movie_list(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MessageResponseSchema | list[MovieCartItemSchema]:
    """
    Shopping cart movie list endpoint.

    Retrieves a list of all the movies in the shopping cart of the current user.

    Args:
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: A message notifying the user that their cart is empty.
        list[MovieCartItemSchema]: A list of all the movies in the shopping cart.
    """
    movies = await get_movies_in_cart(
        user_id=current_user.id, message="No movies in your cart.", db=db
    )
    return movies


@router.get(
    "/{user_id}/",
    response_model=MessageResponseSchema | list[MovieCartItemSchema],
    summary="Admin Get Shopping Cart Movie List",
    description="Retrieves a list of all the movies in the shopping cart by "
    "user's ID if admin makes the request.",
    status_code=status.HTTP_200_OK,
)
async def get_shopping_cart_movie_list(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema | list[MovieCartItemSchema]:
    """
    Shopping cart movie list admin endpoint.

    Retrieves a list of all the movies in the shopping cart of the specified user.

    Args:
        user_id (int): The ID of the owner of the shopping cart items to retrieve.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: A message notifying an admin that the cart is empty.
        list[MovieCartItemSchema]: A list of all the movies in the shopping cart.
    """
    movies = await get_movies_in_cart(
        user_id=user_id, message="No movies in this cart.", db=db
    )
    return movies


@router.delete(
    "/clear/",
    summary="Remove All Cart Items",
    description="Removes all cart items from the user's shopping cart.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        500: {
            "description": "Internal Server Error - An error occurred during cart items deletion.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred when clearing the shopping cart."
                    },
                }
            },
        },
    },
)
async def clear_all_cart_items(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Cart items removal endpoint.

    Clears the current user's cart of all the items in it.

    Args:
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Raises:
        HTTPException:
            - 500 if an error occurred during cart items deletion.
    """
    cart = await get_or_create_cart_by_user_id(user_id=current_user.id, db=db)
    try:
        for cart_item in cart.cart_items:
            await db.delete(cart_item)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when clearing the shopping cart.",
        )


@router.post(
    "/add/{movie_id}/",
    response_model=CartItemDetail,
    summary="Create a Cart Item",
    description="Creates a cart item with the given movie id.",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "description": "Bad Request - The movie is already in the user's cart.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie already in your cart."}
                }
            },
        },
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
        409: {
            "description": "Conflict - The movie order is paid or pending.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You have already ordered or purchased this movie."
                    },
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during cart item creation.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while adding the movie to the cart."
                    },
                }
            },
        },
    },
)
async def add_cart_item(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CartItemDetail:
    """
    Cart item creation endpoint.

    Adds the specified movie to the cart if available, not purchased and not in
    the cart already.

    Args:
        movie_id (int): The ID of the movie to be added to the cart.
        current_user (User): The current user of the cart.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CartItemDetail: The created cart item information.

    Raises:
        HTTPException:
            - 400 if the movie is already in the user's cart.
            - 404 if the movie with the given ID was not found.
            - 409 if the movie is purchased or the order is pending.
            - 500 if an error occurred during cart item creation.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    if await has_user_order_statuses_for_movie(
        user_id=current_user.id,
        movie_id=movie_id,
        statuses=[OrderStatusEnum.PAID.value, OrderStatusEnum.PENDING.value],
        db=db,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already ordered or purchased this movie.",
        )

    try:
        cart = await get_or_create_cart_by_user_id(user_id=current_user.id, db=db)
        new_cart_item = CartItem(cart_id=cart.id, movie_id=movie_id)
        db.add(new_cart_item)
        await db.commit()
        await db.refresh(new_cart_item)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Movie already in your cart.",
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding the movie to the cart.",
        )

    return CartItemDetail.model_validate(new_cart_item)


@router.delete(
    "/remove/{cart_item_id}/",
    summary="Delete Cart Item",
    description="Removes the specified cart item from the cart.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {
            "description": "Forbidden - Cart Item does not belong to user.",
            "content": {
                "application/json": {
                    "example": {"detail": "You cannot modify this cart item."}
                }
            },
        },
        404: {
            "description": "Not Found - Cart Item with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Cart item not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during cart item deletion.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while removing the cart item."
                    },
                }
            },
        },
    },
)
async def remove_cart_item(
    cart_item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cart Item deletion endpoint.

    Removes the given cart item from the current user's cart.

    Args:
        cart_item_id (int): The ID of the cart item to be removed.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Raises:
        HTTPException:
            - 403 if the cart item does not belong to the current user.
            - 404 if cart item with the given ID was not found.
            - 500 if an error occurred during cart item deletion.
    """
    cart_item = await get_cart_item_by_id(cart_item_id, db)
    cart = await get_or_create_cart_by_user_id(user_id=current_user.id, db=db)
    if cart_item.cart_id != cart.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot modify this cart item.",
        )

    try:
        await db.delete(cart_item)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while removing the cart item.",
        )

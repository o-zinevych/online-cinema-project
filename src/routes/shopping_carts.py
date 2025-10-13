from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from database import get_db
from database.models import Cart, CartItem
from database.models.accounts import User
from database.models.orders import OrderStatusEnum
from routes.movies import get_movie_by_id_stmt, movie_not_found_exception
from routes.orders import has_user_order_statuses_for_movie
from schemas.shopping_carts import CartItemDetail
from security.account_utils import get_current_user

router = APIRouter()


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
    stmt = select(Cart).where(Cart.user_id == user_id)
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

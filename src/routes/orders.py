from decimal import Decimal

from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy import delete, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from database import get_db
from database.models import User, CartItem, Order
from database.models.orders import OrderStatusEnum, OrderItem
from schemas.movies import MovieSchema
from schemas.orders import OrderDetailSchema
from services.account_utils import get_current_user
from services.order_utils import get_total_price_of_ordered_movies
from services.shopping_cart_utils import (
    get_or_create_cart_by_user_id,
    get_cart_item_movie_ids,
    get_movies_in_cart,
)

router = APIRouter()


@router.post(
    "/place/",
    response_model=OrderDetailSchema,
    summary="Create an Order",
    description="Creates an order for all the shopping cart items.",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "description": "Bad Request - Shopping cart movies unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "No available movies in your cart."}
                }
            },
        },
        404: {
            "description": "Not Found - User's shopping cart is empty.",
            "content": {
                "application/json": {"example": {"detail": "Shopping cart is empty."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during order creation.",
            "content": {
                "application/json": {
                    "examples": {
                        "cart_item_removal_error": {
                            "summary": "Cart Item Removal Error",
                            "value": {
                                "detail": "An error occurred while removing the cart items."
                            },
                        },
                        "order_db_error": {
                            "summary": "Order Creation Error",
                            "value": {
                                "detail": "An error occurred while placing the order."
                            },
                        },
                    },
                }
            },
        },
    },
)
async def create_order(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> OrderDetailSchema:
    """
    Order creation endpoint.

    Checks that all movies are available to order and removes the unavailable items
    from the shopping cart notifying the user.
    Sets the total amount to be paid when creating an order for all the shopping cart
    items of the current user and removes them after successful creation.

    Args:
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        OrderDetailSchema: The new order information.

    Raises:
        HTTPException:
            - 400 if no movies in the cart are available.
            - 404 if the user's shopping cart is empty.
            - 500 if an error occurred while deleting an unavailable movie cart item
            or placing a new order.
    """
    cart = await get_or_create_cart_by_user_id(user_id=current_user.id, db=db)
    if not cart.cart_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Shopping cart is empty."
        )

    available_movies = await get_movies_in_cart(user_id=current_user.id, db=db)
    cart_movie_ids = await get_cart_item_movie_ids(cart_id=cart.id, db=db)
    available_movies_ids = [movie.id for movie in available_movies]
    missing_ids = set(cart_movie_ids) - set(available_movies_ids)

    message = None
    cart_item_exception = HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An error occurred while removing the cart items.",
    )

    if missing_ids:
        try:
            delete_stmt = delete(CartItem).where(
                and_(CartItem.cart_id == cart.id, CartItem.movie_id.in_(missing_ids))
            )
            await db.execute(delete_stmt)
            await db.commit()
            if not available_movies:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No available movies in your cart.",
                )
            message = "Some unavailable movies have been removed from your cart."
        except SQLAlchemyError:
            await db.rollback()
            raise cart_item_exception

    try:
        new_order = Order(user_id=current_user.id, status=OrderStatusEnum.PENDING)
        db.add(new_order)
        await db.flush()

        order_items = [
            OrderItem(
                order_id=new_order.id,
                movie_id=movie.id,
                price_at_order=movie.price or Decimal("0.00"),
            )
            for movie in available_movies
        ]
        db.add_all(order_items)

        total_price = get_total_price_of_ordered_movies(available_movies)
        new_order.total_amount = total_price

        await db.commit()
        await db.refresh(new_order)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while placing the order.",
        )

    try:
        delete_stmt = delete(CartItem).where(CartItem.cart_id == cart.id)
        await db.execute(delete_stmt)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise cart_item_exception

    movies = [MovieSchema.model_validate(movie) for movie in available_movies]
    return OrderDetailSchema(
        id=new_order.id,
        created_at=new_order.created_at,
        movies=movies,
        total_amount=new_order.total_amount,
        status=new_order.status,
        message=message,
    )

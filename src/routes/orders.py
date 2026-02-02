from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, APIRouter, HTTPException, Query
from sqlalchemy import delete, and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from database import get_db
from database.models import User, CartItem, Order
from database.models.orders import OrderStatusEnum, OrderItem
from schemas.common import MessageResponseSchema
from schemas.movies import MovieSchema
from schemas.orders import (
    OrderCreateResponseSchema,
    OrderListResponseSchema,
    OrderDetailSchema,
    AdminOrderFilterParams,
)
from services.account_utils import get_current_user, require_admin
from services.common_utils import (
    apply_limit_offset_to_item_list,
    count_total_items,
    count_total_pages,
)
from services.order_utils import (
    get_total_price_of_ordered_movies,
    no_orders_exception,
    order_not_found_exception,
    cancelled_order_exception,
    paid_order_exception,
    add_filters_to_order_list_page_links,
)
from services.shopping_cart_utils import (
    get_or_create_cart_by_user_id,
    get_cart_item_movie_ids,
    get_movies_in_cart,
)

router = APIRouter()


@router.get(
    "/",
    response_model=OrderListResponseSchema,
    summary="Admin Order List",
    description="Get all orders filtered by user, date, and status if admin.",
    status_code=status.HTTP_200_OK,
    responses={
        403: {
            "description": "Forbidden - Only admin users can perform this action.",
            "content": {
                "application/json": {
                    "example": {"detail": "You must be an admin to do this."}
                }
            },
        },
        404: {
            "description": "Not Found - User has no orders.",
            "content": {
                "application/json": {"example": {"detail": "No orders found."}}
            },
        },
    },
)
async def get_user_orders(
    filter_params: Annotated[AdminOrderFilterParams, Query()],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponseSchema:
    """
    Admin order list endpoint.

    Lets admin users view paginated orders and apply user ID, date and status
    filters to them.

    Args:
        filter_params (Annotated[AdminOrderFilterParams, Query]): Filters to apply
        to the list.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        OrderListResponseSchema: The paginated and filtered list of orders.

    Raises:
        HTTPException:
            - 403 if the current user is not an admin.
            - 404 if no orders are found.
    """
    order_stmt = select(Order).options(
        selectinload(Order.order_items).selectinload(OrderItem.movie)
    )

    if filter_params.user_id:
        order_stmt = order_stmt.filter(Order.user_id == filter_params.user_id)
    if filter_params.date:
        start_of_day = datetime.combine(filter_params.date, datetime.min.time())
        end_of_day = datetime.combine(filter_params.date, datetime.max.time())

        order_stmt = order_stmt.where(
            Order.created_at >= start_of_day,
            Order.created_at < end_of_day,
        )
    if filter_params.status:
        order_stmt = order_stmt.filter(Order.status == filter_params.status)

    total_items = await count_total_items(order_stmt, db)
    if not total_items:
        raise no_orders_exception

    order_list = await apply_limit_offset_to_item_list(
        stmt=order_stmt,
        page=filter_params.page,
        per_page=filter_params.per_page,
        error_to_raise=no_orders_exception,
        list_item_schema=OrderDetailSchema,
        db=db,
    )

    total_pages = count_total_pages(total_items, filter_params.per_page)
    prev_page = (
        add_filters_to_order_list_page_links(
            f"/orders/?page={filter_params.page - 1}&per_page={filter_params.per_page}",
            filter_params,
        )
        if filter_params.page > 1
        else None
    )
    next_page = (
        add_filters_to_order_list_page_links(
            f"/orders/?page={filter_params.page + 1}&per_page={filter_params.per_page}",
            filter_params,
        )
        if filter_params.page < total_pages
        else None
    )

    result = {
        "orders": order_list,
        "prev_page": prev_page,
        "next_page": next_page,
        "total_pages": total_pages,
        "total_items": total_items,
    }
    return OrderListResponseSchema(**result)


@router.post(
    "/place/",
    response_model=OrderCreateResponseSchema,
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
) -> OrderCreateResponseSchema:
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
        OrderCreateResponseSchema: The new order information.

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
    return OrderCreateResponseSchema(
        id=new_order.id,
        created_at=new_order.created_at,
        movies=movies,
        total_amount=new_order.total_amount,
        status=new_order.status,
        message=message,
    )


@router.get(
    "/my-orders/",
    response_model=OrderListResponseSchema,
    summary="Get Your Orders",
    description="Retrieves current user's orders with pagination.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not Found - User has no orders.",
            "content": {
                "application/json": {"example": {"detail": "No orders found."}}
            },
        },
    },
)
async def get_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(5, ge=1, le=15),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponseSchema:
    """
    Order list endpoint.

    Retrieves current user's orders with pagination.

    Args:
        page: Page number.
        per_page: Number of items per page.
        current_user: The current user of the request.
        db (AsyncSession): Async database session.

    Returns:
        OrderListResponseSchema: Order list response with links to previous
        and next pages if available.

    Raises:
        HTTPException:
            - 404 if the current user has no orders.
    """
    order_stmt = (
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(selectinload(Order.order_items).selectinload(OrderItem.movie))
    )
    total_items = await count_total_items(order_stmt, db)
    if not total_items:
        raise no_orders_exception

    order_list = await apply_limit_offset_to_item_list(
        stmt=order_stmt,
        page=page,
        per_page=per_page,
        error_to_raise=no_orders_exception,
        list_item_schema=OrderDetailSchema,
        db=db,
    )

    total_pages = count_total_pages(total_items, per_page)
    base_url = "/my-orders/"
    prev_page = f"{base_url}?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = (
        f"{base_url}?page={page + 1}&per_page={per_page}"
        if page < total_pages
        else None
    )

    result = {
        "orders": order_list,
        "prev_page": prev_page,
        "next_page": next_page,
        "total_pages": total_pages,
        "total_items": total_items,
    }
    return OrderListResponseSchema(**result)


@router.post(
    "/my-orders/{order_id}/cancel/",
    response_model=MessageResponseSchema,
    summary="Cancel Order",
    description="Cancel an existing pending order.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - The given order is already canceled or paid.",
            "content": {
                "application/json": {
                    "examples": {
                        "canceled_order": {
                            "summary": "Order Already Canceled",
                            "value": {
                                "detail": "This order has already been canceled."
                            },
                        },
                        "paid_order": {
                            "summary": "Order Already Paid For",
                            "value": {"detail": "No movies found."},
                        },
                    }
                }
            },
        },
        404: {
            "description": "Not Found - Order with the given ID not found.",
            "content": {
                "application/json": {"example": {"detail": "Order not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during order "
            "cancellation.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when canceling the order."}
                }
            },
        },
    },
)
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Order cancellation endpoint.

    Allows authenticated users to cancel their pending order.
    If the order has been paid, prompts the user to submit a refund request.
    If the order has been canceled already, raises an error.

    Args:
        order_id: The ID of the order to cancel.
        current_user: The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message response notifying the user about successful
        cancellation or the need to submit a refund request.

    Raises:
        HTTPException:
            - 400 if the given order has already been canceled or paid for.
            - 404 if the order to be cancelled was not found or does not belong
            to the current user.
            - 500 if an error occurred during order cancellation.
    """
    order_stmt = select(Order).where(Order.id == order_id)
    order_result = await db.execute(order_stmt)
    order = order_result.scalar_one_or_none()
    if not order or order.user_id != current_user.id:
        raise order_not_found_exception

    if order.status == OrderStatusEnum.CANCELED:
        raise cancelled_order_exception

    if order.status == OrderStatusEnum.PAID:
        raise paid_order_exception

    try:
        order.status = OrderStatusEnum.CANCELED
        await db.commit()
        return MessageResponseSchema(
            message=f"Order {order_id} has been canceled successfully."
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when canceling the order.",
        )

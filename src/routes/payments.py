import stripe
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.dependencies import get_settings
from database import get_db
from database.models import User
from database.models.orders import OrderStatusEnum
from schemas.common import MessageResponseSchema
from schemas.payments import PaymentCheckoutResponseSchema
from services.account_utils import get_current_user
from services.order_utils import (
    get_order_by_id,
    order_not_found_exception,
    order_not_pending_exception,
)
from services.payment_utils import create_payment_and_payment_items

router = APIRouter()

settings = get_settings()
stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post(
    "/checkout/{order_id}/",
    response_model=PaymentCheckoutResponseSchema,
    summary="Payment Checkout",
    description="Creates a checkout session redirecting user to pay.",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {
            "description": "Forbidden - Order is not pending.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "The order has already been paid for or canceled."
                    }
                }
            },
        },
        404: {
            "description": "Not Found - Order with the given ID was not found.",
            "content": {
                "application/json": {"example": {"detail": "Order not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error during payment creation.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when making the purchase."}
                }
            },
        },
    },
)
async def create_checkout_session(
    order_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentCheckoutResponseSchema:
    """
    Checkout session creation endpoint.

    Checks that the order with the given ID exists and belongs to the user.
    Creates a checkout session with the given data.
    If the movies in the cart are free, creates a successful payment immediately.

    Args:
        order_id (int): The ID of the order to pay for.
        request (Request): The incoming HTTP request.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        PaymentCheckoutResponseSchema: Response containing the checkout url
        redirecting the user.

    Raises:
        HTTPException:
            - 403 if the order has already been paid for.
            - 404 if the order to be paid for was not found or does not belong
            to the current user
            - 500 if an error occurred when creating the payment and its items.
    """
    order = await get_order_by_id(order_id=order_id, db=db)
    if not order or order.user_id != current_user.id:
        raise order_not_found_exception

    if order.status != OrderStatusEnum.PENDING:
        raise order_not_pending_exception

    total_amount = order.total_amount
    if total_amount == 0:
        try:
            await create_payment_and_payment_items(
                user_id=current_user.id,
                order_id=order_id,
                amount=total_amount,
                order_items=order.order_items,
                db=db,
            )
            order.status = OrderStatusEnum.PAID
            await db.commit()
            return PaymentCheckoutResponseSchema(
                checkout_url=None, message="Movies have been successfully purchased."
            )
        except SQLAlchemyError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred when making the purchase.",
            )

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price_data": {
                        "currency": "USD",
                        "product_data": {"name": "Movie Order"},
                        "unit_amount": int(total_amount * 100),
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "user_id": current_user.id,
                "user_email": current_user.email,
                "order_id": order.id,
            },
            mode="payment",
            success_url=str(request.url_for("payment_success", order_id=order.id))
            + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.url_for("payment_cancel", order_id=order.id),
        )

        return PaymentCheckoutResponseSchema(checkout_url=checkout_session.url)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        )


@router.get(
    "/checkout/{order_id}/success/",
    response_model=MessageResponseSchema,
    summary="Payment Success",
    description="Informs the user about a successful payment.",
    status_code=status.HTTP_200_OK,
    name="payment_success",
    responses={
        403: {
            "description": "Forbidden - Order is not pending.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "The order has already been paid for or canceled."
                    }
                }
            },
        },
        404: {
            "description": "Not Found - Order with the given ID was not found.",
            "content": {
                "application/json": {"example": {"detail": "Order not found."}}
            },
        },
    },
)
async def payment_success(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Payment checkout success endpoint.

    Checkout session success url redirects to this endpoint.

    Args:
        order_id (int): The ID of the order being paid for.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message about successful payment completion.
    """
    order = await get_order_by_id(order_id=order_id, db=db)
    if not order or order.user_id != current_user.id:
        raise order_not_found_exception

    if order.status != OrderStatusEnum.PENDING:
        raise order_not_pending_exception

    return MessageResponseSchema(message="Payment completed successfully.")


@router.get(
    "/checkout/{order_id}/cancel/",
    response_model=MessageResponseSchema,
    summary="Payment Cancel",
    description="Informs the user about a payment cancellation.",
    status_code=status.HTTP_200_OK,
    name="payment_cancel",
    responses={
        403: {
            "description": "Forbidden - Order is not pending.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "The order has already been paid for or canceled."
                    }
                }
            },
        },
        404: {
            "description": "Not Found - Order with the given ID was not found.",
            "content": {
                "application/json": {"example": {"detail": "Order not found."}}
            },
        },
    },
)
async def payment_cancel(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Payment checkout cancel endpoint.

    Checkout session cancel url redirects to this endpoint.

    Args:
        order_id (int): The ID of the order being paid for.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message about checkout cancellation.
    """
    order = await get_order_by_id(order_id=order_id, db=db)
    if not order or order.user_id != current_user.id:
        raise order_not_found_exception

    if order.status != OrderStatusEnum.PENDING:
        raise order_not_pending_exception
    return MessageResponseSchema(message="Payment canceled.")

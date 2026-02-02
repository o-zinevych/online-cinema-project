import stripe
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from stripe import SignatureVerificationError

from config.dependencies import get_settings, get_account_email_sender
from database import get_db
from database.models import User, Payment
from database.models.orders import OrderStatusEnum
from schemas.common import MessageResponseSchema
from schemas.payments import (
    PaymentCheckoutResponseSchema,
    PaymentListResponseSchema,
    PaymentDetailSchema,
)
from services.account_utils import get_current_user
from services.common_utils import (
    count_total_items,
    apply_limit_offset_to_item_list,
    count_total_pages,
)
from services.order_utils import (
    get_order_by_id,
    order_not_found_exception,
    order_not_pending_exception,
)
from services.payment_utils import (
    create_payment_and_payment_items,
    no_payments_exception,
)

router = APIRouter()

settings = get_settings()
stripe.api_key = settings.STRIPE_SECRET_KEY

email_sender = get_account_email_sender(settings)


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


@router.post(
    "/webhook/",
    response_model=MessageResponseSchema,
    summary="Stripe Webhook",
    description="Creates a new payment and updates order status after successful checkout.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Stripe signature not valid.",
            "content": {
                "application/json": {"example": {"detail": "Invalid signature."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error during payment creation.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred when creating a payment record."
                    }
                }
            },
        },
    },
)
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema | None:
    """
    Stripe Webhook endpoint.

    Checks the  Stripe signature and constructs the event if valid.
    If the checkout session is completed, creates a payment and its payment items
    in the database. Updates the Order payment status to PAID and sends a
    corresponding email notification.
    If the charge was unsuccessful, suggests the user try a different payment
    method.

    Args:
        request (Request): The incoming HTTP request.
        background_tasks (BackgroundTasks): Background tasks to schedule the
        email notification about payment success to be sent.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message about successful payment completion.

    Raises:
        HTTPException:
            - 400 if the Stripe signature is invalid.
            - 500 if an error occurred when creating a payment or payment item.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, SignatureVerificationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature."
        )

    if event["type"] == "checkout.session.completed":
        try:
            session = event["data"]["object"]
            order_id = session["metadata"].get("order_id")
            order = await get_order_by_id(order_id=order_id, db=db)
            await create_payment_and_payment_items(
                user_id=session["metadata"].get("user_id"),
                order_id=order_id,
                amount=order.total_amount,
                order_items=order.order_items,
                db=db,
            )
            order.status = OrderStatusEnum.PAID
            await db.commit()

            user_email = session["metadata"].get("user_email")
            background_tasks.add_task(
                email_sender.send_payment_complete_email, user_email, order_id
            )

            return MessageResponseSchema(message="Payment completed successfully.")
        except SQLAlchemyError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred when creating a payment record.",
            )

    if event["type"] == "charge.failed":
        return MessageResponseSchema(
            message="Payment failed. Try a different payment method."
        )


@router.get(
    "/my-payments/",
    response_model=PaymentListResponseSchema,
    summary="Get Your Payments",
    description="Retrieves current user's payment history with pagination.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not Found - User has no payments.",
            "content": {
                "application/json": {"example": {"detail": "No payments found."}}
            },
        },
    },
)
async def get_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(5, ge=1, le=15),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentListResponseSchema:
    """
    Payment list endpoint.

    Retrieves current user's payment history with pagination.

    Args:
        page: Page number.
        per_page: Number of items per page.
        current_user: The current user of the request.
        db (AsyncSession): Async database session.

    Returns:
        PaymentListResponseSchema: Payment list response with links to previous
        and next pages if available.

    Raises:
        HTTPException:
            - 404 if the current user has no payments.
    """
    payment_stmt = select(Payment).where(Payment.user_id == current_user.id)
    total_items = await count_total_items(payment_stmt, db)
    if not total_items:
        raise no_payments_exception

    payment_list = await apply_limit_offset_to_item_list(
        stmt=payment_stmt,
        page=page,
        per_page=per_page,
        error_to_raise=no_payments_exception,
        list_item_schema=PaymentDetailSchema,
        db=db,
    )

    total_pages = count_total_pages(total_items, per_page)
    base_url = "/my-payments/"
    prev_page = f"{base_url}?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = (
        f"{base_url}?page={page + 1}&per_page={per_page}"
        if page < total_pages
        else None
    )

    result = {
        "payments": payment_list,
        "prev_page": prev_page,
        "next_page": next_page,
        "total_pages": total_pages,
        "total_items": total_items,
    }
    return PaymentListResponseSchema(**result)

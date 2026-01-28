from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, OrderItem
from database.models.payments import PaymentStatusEnum, PaymentItem


async def create_payment_and_payment_items(
    user_id: int,
    order_id: int,
    amount: Decimal,
    order_items: list[OrderItem],
    db: AsyncSession,
) -> Payment:
    """
    Creates a payment and its corresponding payment items.

    Args:
        user_id (int): The ID of the user making the payment.
        order_id (int): The ID of the order for which the payment is made.
        amount (Decimal): The total amount of the payment.
        order_items (list[OrderItem]): The order items to create payment items for.
        db (AsyncSession): Asynchronous database session.

    Returns:
        Payment: The payment that was created.
    """
    payment = Payment(
        user_id=user_id,
        order_id=order_id,
        status=PaymentStatusEnum.SUCCESSFUL,
        amount=amount,
    )
    db.add(payment)
    await db.flush()

    for order_item in order_items:
        payment_item = PaymentItem(
            payment_id=payment.id,
            order_item_id=order_item.id,
            price_at_payment=order_item.price_at_order,
        )
        db.add(payment_item)

    return payment

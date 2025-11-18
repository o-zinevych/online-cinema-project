import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, ForeignKey, DateTime, func, Enum, DECIMAL, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


class PaymentStatusEnum(str, enum.Enum):
    SUCCESSFUL = "successful"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[PaymentStatusEnum] = mapped_column(
        Enum(PaymentStatusEnum), default=PaymentStatusEnum.SUCCESSFUL, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    external_payment_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="payments")
    order: Mapped["Order"] = relationship("Order", back_populates="payments")
    payment_items: Mapped[list["PaymentItem"]] = relationship(
        "PaymentItem", back_populates="payment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"Payment(id={self.id}, user_id={self.user_id}, order_id={self.order_id})"
        )


class PaymentItem(Base):
    __tablename__ = "payment_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False
    )
    price_at_payment: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)

    payment: Mapped["Payment"] = relationship("Payment", back_populates="payment_items")
    order_item: Mapped["OrderItem"] = relationship(
        "OrderItem", back_populates="payment_items"
    )

    def __repr__(self) -> str:
        return f"PaymentItem(id={self.id}, payment_id={self.payment_id}, order_item_id={self.order_item_id})"

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from database.models.payments import PaymentStatusEnum


class PaymentCheckoutResponseSchema(BaseModel):
    checkout_url: Optional[str] = None
    message: str = "Redirecting the user to checkout."


class PaymentDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    amount: Decimal
    status: PaymentStatusEnum


class AdminPaymentDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    order_id: int
    created_at: datetime
    status: PaymentStatusEnum
    amount: Decimal
    external_payment_id: Optional[str] = None


class PaymentListResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payments: List[PaymentDetailSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int


class AdminPaymentListResponseSchema(PaymentListResponseSchema):
    payments: List[AdminPaymentDetailSchema]

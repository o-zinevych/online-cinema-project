from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from database.models.orders import OrderStatusEnum
from schemas.movies import MovieSchema


class OrderDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    movies: List[MovieSchema]
    total_amount: Optional[Decimal] = None
    status: OrderStatusEnum


class OrderCreateResponseSchema(OrderDetailSchema):
    message: Optional[str] = None


class OrderListResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orders: List[OrderDetailSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CartItemDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cart_id: int
    movie_id: int
    added_at: datetime

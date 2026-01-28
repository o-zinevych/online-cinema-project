from typing import Optional

from pydantic import BaseModel


class PaymentCheckoutResponseSchema(BaseModel):
    checkout_url: Optional[str] = None
    message: str = "Redirecting the user to checkout."

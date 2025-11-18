from fastapi import FastAPI

from routes import accounts, movies, shopping_carts, orders

app = FastAPI(
    title="Cinema API",
    description="An online cinema API that allows users to select, watch, and "
    "purchase access to movies as well as manage their accounts.",
)

api_version_prefix = "/api/v1/cinema"

app.include_router(
    accounts.router, prefix=f"{api_version_prefix}/accounts", tags=["accounts"]
)
app.include_router(movies.router, prefix=f"{api_version_prefix}", tags=["cinema"])
app.include_router(
    shopping_carts.router,
    prefix=f"{api_version_prefix}/shopping_cart",
    tags=["shopping_cart"],
)
app.include_router(
    orders.router, prefix=f"{api_version_prefix}/orders", tags=["orders"]
)

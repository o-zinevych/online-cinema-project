from fastapi import FastAPI

from routes import accounts, movies

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

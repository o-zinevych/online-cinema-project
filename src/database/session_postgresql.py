from typing import Any, AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from config.dependencies import get_settings

settings = get_settings()

POSTGRESQL_DATABASE_URL = (
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_DB_PORT}/{settings.POSTGRES_DB}"
)
postgresql_engine = create_async_engine(POSTGRESQL_DATABASE_URL, echo=False)
# noinspection PyTypeChecker
AsyncPostgresqlSessionLocal = sessionmaker(
    bind=postgresql_engine, class_=AsyncSession, expire_on_commit=False
)

sync_database_url = POSTGRESQL_DATABASE_URL.replace("+asyncpg", "")
sync_postgresql_engine = create_engine(sync_database_url, echo=False)


async def get_postgresql_db() -> AsyncGenerator[Any, Any]:
    """
    Returns:
        AsyncGenerator: An asynchronous generator that yields a new database
        session ensuring it closes after use.
    """
    async with AsyncPostgresqlSessionLocal() as session:
        yield session

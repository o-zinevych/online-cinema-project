from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from config.dependencies import get_settings

settings = get_settings()

SQLITE_DATABASE_URL = f"sqlite+aiosqlite:///{settings.PATH_TO_DB}"
sqlite_engine = create_async_engine(
    SQLITE_DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)
# noinspection PyTypeChecker
AsyncSQLiteSessionLocal = sessionmaker(
    bind=sqlite_engine, class_=AsyncSession, expire_on_commit=False
)

sync_database_url = SQLITE_DATABASE_URL.replace("+aiosqlite", "")
sync_sqlite_engine = create_engine(
    sync_database_url, echo=False, connect_args={"check_same_thread": False}
)


async def get_sqlite_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Returns:
        AsyncGenerator[AsyncSession, None]: An asynchronous generator that yields
        a new database session ensuring it closes after use.
    """
    async with AsyncSQLiteSessionLocal() as session:
        yield session

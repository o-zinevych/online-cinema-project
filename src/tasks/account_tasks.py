import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete

from database.models.accounts import ActivationToken
from database.session_sqlite import AsyncSQLiteSessionLocal
from tasks.celery_app import celery


@celery.task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 5})
def remove_expired_activation_tokens(self):
    asyncio.run(_remove_expired_activation_tokens())


async def _remove_expired_activation_tokens():
    async with AsyncSQLiteSessionLocal() as session:
        try:
            utc_now = datetime.now(timezone.utc)
            result = await session.execute(
                delete(ActivationToken).where(ActivationToken.expires_at < utc_now)
            )
            delete_count = result.rowcount
            await session.commit()
            print(f"Removed {delete_count} expired activation tokens successfully.")
        except Exception as error:
            await session.rollback()
            print(f"An error occurred during activation token cleanup: {error}")
            raise

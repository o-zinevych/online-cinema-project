from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.dependencies import get_jwt_auth_manager
from database import get_db
from database.models.accounts import User, UserGroup, UserGroupEnum
from security.token_manager import JWTAuthManager

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_user_by_email(email: str, db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    jwt_manager: JWTAuthManager = Depends(get_jwt_auth_manager),
) -> User:
    """
    Retrieves the current user by decoding the JWT access token.

    Args:
        token (str): JWT access token.
        db (AsyncSession): Asynchronous database session.
        jwt_manager (JWTAuthManager): JWT auth manager to decode the token.

    Returns:
        User: The current user.

    Raises:
        HTTPException:
            - 401 Unauthorized if the token does not contain user id.
            - 404 Not Found if user with the given id was not found.
    """
    payload = jwt_manager.decode_access_token(token)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return db_user


async def require_moderator_or_admin(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> User:
    """
    Checks that the current user is either a moderator or admin.

    Args:
        current_user (User): The current user.
        db (AsyncSession): Asynchronous database session.

    Returns:
        User: The current user.
    """
    moderator_stmt = select(UserGroup).where(UserGroup.name == UserGroupEnum.MODERATOR)
    moderator_result = await db.execute(moderator_stmt)
    moderator_group = moderator_result.scalars().first()

    admin_stmt = select(UserGroup).where(UserGroup.name == UserGroupEnum.ADMIN)
    admin_result = await db.execute(admin_stmt)
    admin_group = admin_result.scalars().first()

    if (
        current_user.group_id == moderator_group.id
        or current_user.group_id == admin_group.id
    ):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You must be a moderator or admin to do this.",
    )


async def require_admin(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> User:
    """
    Checks that the current user is an admin.

    Args:
        current_user (User): The current user.
        db (AsyncSession): Asynchronous database session.

    Returns:
        User: The current user.
    """
    result = await db.execute(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.ADMIN)
    )
    admin_group = result.scalars().first()
    if current_user.group_id != admin_group.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be an administrator to do this.",
        )
    return current_user

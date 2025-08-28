from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from database import get_db
from database.models.accounts import User, UserGroup, UserGroupEnum
from schemas.accounts import (
    UserRegistrationResponseSchema,
    UserRegistrationRequestSchema,
)

router = APIRouter()


@router.post(
    "/register/",
    response_model=UserRegistrationResponseSchema,
    summary="User Registration",
    description="Register a new user using an email and password.",
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "Conflict - User already exists.",
            "content": {
                "application/json": {
                    "example": {"detail": "User with this email is already registered."}
                }
            },
        },
        500: {
            "description": "Internal Server Error - Default user group wasn't found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Default user group not found."}
                }
            },
        },
    },
)
async def register_user(
    user_data: UserRegistrationRequestSchema, db: AsyncSession = Depends(get_db)
) -> UserRegistrationResponseSchema:
    result = await db.execute(select(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email is already registered.",
        )

    result = await db.execute(select(UserGroup.name == UserGroupEnum.USER))
    default_user_group = result.scalar_one_or_none()
    if not default_user_group:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default user group not found.",
        )

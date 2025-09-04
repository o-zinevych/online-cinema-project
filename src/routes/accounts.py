from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from database import get_db
from database.models.accounts import User, UserGroup, UserGroupEnum, ActivationToken
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
            "description": "Internal Server Error - An error occurred during user creation.",
            "content": {
                "application/json": {
                    "examples": {
                        "default_user_group_not_found": {
                            "summary": "Default User Group Not Found",
                            "value": {"detail": "Default user group not found."},
                        },
                        "db_error": {
                            "summary": "User Creation Error",
                            "value": {
                                "detail": "An error occurred during user registration."
                            },
                        },
                    }
                }
            },
        },
    },
)
async def register_user(
    user_data: UserRegistrationRequestSchema, db: AsyncSession = Depends(get_db)
) -> UserRegistrationResponseSchema:
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email is already registered.",
        )

    result = await db.execute(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    )
    default_user_group = result.scalar_one_or_none()
    if not default_user_group:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default user group not found.",
        )

    try:
        new_user = User.create(
            email=str(user_data.email),
            raw_password=user_data.password,
            group_id=default_user_group.id,
        )
        db.add(new_user)
        await db.flush()

        activation_token = ActivationToken(user_id=new_user.id)
        db.add(activation_token)

        await db.commit()
        await db.refresh(new_user)
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during user registration.",
        ) from error
    else:
        return UserRegistrationResponseSchema.model_validate(new_user)

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from starlette import status

from config.dependencies import get_account_email_sender, get_settings
from database import get_db
from database.models.accounts import (
    User,
    UserGroup,
    UserGroupEnum,
    ActivationToken,
)
from schemas.accounts import (
    UserRegistrationResponseSchema,
    UserRegistrationRequestSchema,
    UserActivationRequestSchema,
    MessageResponseSchema,
)

router = APIRouter()

settings = get_settings()
base_url = "http://127.0.0.1:8000/api/v1/cinema/accounts"
email_sender = get_account_email_sender(settings)


async def get_user_by_email(email: str, db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    return user


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
    user_data: UserRegistrationRequestSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> UserRegistrationResponseSchema:
    """
    User registration endpoint.

    Registers a new user via email, hashes their password and assigns them the default user group.
    Also sends an email notification with the account activation link.
    If a user with the same email is already registered, an HTTP 409 error is raised.
    If any unexpected errors happen during the creation process, an HTTP 500 error is raised.

    Args:
        user_data (UserRegistrationRequestSchema): User registration details including their email and password.
        background_tasks (BackgroundTasks): Background tasks to schedule the email to be sent when registered.
        db (AsyncSession): Asynchronous database session.

    Returns:
        UserRegistrationResponseSchema: The new user's details.

    Raises:
        HTTPException:
            - 409 Conflict if a user with the same email exists.
            - 500 Internal Server Error if an error occurred during user creation.
    """
    existing_user = await get_user_by_email(str(user_data.email), db)
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
        await db.flush()

        activation_link = f"{base_url}/activate/?token={activation_token.token}"
        background_tasks.add_task(
            email_sender.send_activation_email, new_user.email, activation_link
        )

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


@router.get(
    "/activate/",
    response_model=MessageResponseSchema,
    summary="User Account Activation",
    description="Activate an existing user account using an email and password.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Invalid or expired token.",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_token": {
                            "summary": "Invalid Token Provided",
                            "value": "Invalid token. Please visit the following link to request a new one: {resend_link}",
                        },
                        "expired_token": {
                            "summary": "Expired Token Provided",
                            "value": "Token expired. Please visit the following link to request a new one: {resend_link}",
                        },
                        "account_active": {
                            "summary": "Account Already Active",
                            "value": "This user account is already active.",
                        },
                    }
                }
            },
        },
    },
)
async def activate_account(
    token: str = Query(...), db: AsyncSession = Depends(get_db)
) -> MessageResponseSchema:
    """
    Account activation endpoint.

    Activates an existing user account using the token provided as query parameter.
    If the token is invalid, expired or the account is already active, an HTTP 400 error is raised.

    Args:
        token (str): The activation token to use.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: A response message confirming successful activation.

    Raises:
        HTTPException:
            - 400 Bad Request if the token is invalid or expired.
            - 400 Bad Request if the user account is already active.
    """
    result = await db.execute(
        select(ActivationToken)
        .options(joinedload(ActivationToken.user))
        .where(ActivationToken.token == token)
    )
    token_record = result.scalar_one_or_none()
    resend_link = f"{base_url}/activate/request/"

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid token. Please visit the following link to request a new one: {resend_link}",
        )

    now_utc = datetime.now(timezone.utc)
    if token_record.expires_at.replace(tzinfo=timezone.utc) < now_utc:
        await db.delete(token_record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token expired. Please visit the following link to request a new one: {resend_link}",
        )

    user = token_record.user
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user account is already active.",
        )
    user.is_active = True
    await db.delete(token_record)
    await db.commit()
    return MessageResponseSchema(message="User account activated successfully.")


@router.post(
    "/activate/request/",
    response_model=MessageResponseSchema,
    summary="Account Activation Request",
    description="Request a new account activation link to be sent to a given email.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Account already active.",
            "content": {
                "application/json": {
                    "example": {"detail": "This user account is already active."}
                }
            },
        },
        404: {
            "description": "Not Found - User with the given email was not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "User with the given email not found."}
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during token creation.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred during activation link generation."
                    }
                }
            },
        },
    },
)
async def request_account_activation_link(
    user_data: UserActivationRequestSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    New account activation link endpoint.

    Sends a fresh activation link to the given email if that account is not active yet.
    In the process, deletes any existing activation tokens for the given user.

    Args:
        user_data (UserActivationRequestSchema): The user's email.
        background_tasks (BackgroundTasks): Background tasks to schedule the activation link email to be sent.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: A response message confirming successful activation.

    Raises:
        HTTPException:
            - 400 Bad Request if the user account is already active.
            - 404 Not Found if the user account was not found.
            - 500 Internal Server Error if an error occurred during activation token creation.
    """
    result = await db.execute(
        select(User)
        .options(joinedload(User.activation_token))
        .where(User.email == user_data.email)
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with the given email not found.",
        )

    if db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user account is already active.",
        )

    existing_token = db_user.activation_token
    if existing_token:
        await db.delete(existing_token)
        await db.commit()
        await db.refresh(db_user)

    try:
        activation_token = ActivationToken(user_id=db_user.id)
        db.add(activation_token)
        await db.commit()

        activation_link = f"{base_url}/activate/?token={activation_token.token}"
        background_tasks.add_task(
            email_sender.send_activation_email, db_user.email, activation_link
        )

    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during activation link generation.",
        ) from error
    return MessageResponseSchema(
        message="Account activation link sent successfully to your email."
    )

import enum
from datetime import datetime, date, timezone, timedelta
from typing import List, Optional

from sqlalchemy import (
    Enum,
    Integer,
    String,
    Boolean,
    DateTime,
    func,
    ForeignKey,
    Date,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base
from security.utils import hash_password, generate_secure_token


class UserGroupEnum(str, enum.Enum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class GenderEnum(str, enum.Enum):
    MAN = "man"
    WOMAN = "woman"


class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[UserGroupEnum] = mapped_column(
        Enum(UserGroupEnum), nullable=False, unique=True
    )

    users: Mapped[List["User"]] = relationship("User", back_populates="group")

    def __repr__(self) -> str:
        return f"UserGroup(id={self.id}, name={self.name})"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    _hashed_password: Mapped[str] = mapped_column(
        "hashed_password", String(255), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False
    )
    group: Mapped["UserGroup"] = relationship("UserGroup", back_populates="users")

    profile: Mapped["UserProfile"] = relationship(
        "UserProfile", back_populates="user", cascade="all, delete-orphan"
    )

    activation_token: Mapped["ActivationToken"] = relationship(
        "ActivationToken", back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_token: Mapped["PasswordResetToken"] = relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_token: Mapped["RefreshToken"] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def password(self) -> None:
        raise AttributeError("Password is write-only.")

    @password.setter
    def password(self, raw_password: str) -> None:
        """Set the user's password after hashing it."""
        self._hashed_password = hash_password(raw_password)

    def __repr__(self) -> str:
        return f"User(id={self.id}, email={self.email}, is_active={self.is_active})"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    avatar: Mapped[Optional[str]] = mapped_column(String(255))
    gender: Mapped[Optional[GenderEnum]] = mapped_column(Enum(GenderEnum))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    info: Mapped[Optional[str]] = mapped_column(Text)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user: Mapped["User"] = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return f"UserProfile(id={self.id}, first_name={self.first_name}, last_name={self.last_name}, date_of_birth={self.date_of_birth})"


class TokenBase(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, default=generate_secure_token
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=1),
    )


class ActivationToken(TokenBase):
    __tablename__ = "activation_tokens"
    __table_args__ = (UniqueConstraint("user_id"),)

    user: Mapped["User"] = relationship("User", back_populates="activation_token")

    def __repr__(self) -> str:
        return f"ActivationToken(user_id={self.user_id}, token={self.token}, expires_at={self.expires_at})"

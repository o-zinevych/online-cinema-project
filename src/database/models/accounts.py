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
    Table,
    Column,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from database.models.base import Base
from database.validators.accounts import validate_password_strength, validate_email
from security.password_utils import (
    hash_password,
    generate_secure_token,
    verify_password,
)


UserMovieFavoritesModel = Table(
    "user_movie_favorites",
    Base.metadata,
    Column(
        "user_id",
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
)


class UserGroupEnum(str, enum.Enum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class GenderEnum(str, enum.Enum):
    MAN = "man"
    WOMAN = "woman"


class ReactionEnum(str, enum.Enum):
    LIKE = "like"
    DISLIKE = "dislike"


class UserMovieReaction(Base):
    __tablename__ = "user_movie_reactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    reaction: Mapped[ReactionEnum] = mapped_column(Enum(ReactionEnum), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="movie_reactions")
    movie: Mapped["Movie"] = relationship("Movie", back_populates="user_reactions")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="user_movie_reaction_unique"),
    )

    def __repr__(self) -> str:
        return f"UserMovieReaction(user_id={self.user_id}, movie_id={self.movie_id}, reaction={self.reaction})"


class UserMovieRating(Base):
    __tablename__ = "user_movie_ratings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="movie_ratings")
    movie: Mapped["Movie"] = relationship("Movie", back_populates="user_ratings")

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 10", name="rating_range_check"),
    )

    def __repr__(self) -> str:
        return f"UserMovieRating(user_id={self.user_id}, movie_id={self.movie_id}, rating={self.rating})"


class UserMovieComment(Base):
    __tablename__ = "user_movie_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    comment: Mapped[str] = mapped_column(String(250), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="movie_comments")
    movie: Mapped["Movie"] = relationship("Movie", back_populates="user_comments")
    comment_replies: Mapped[list["MovieCommentReply"]] = relationship(
        "MovieCommentReply",
        back_populates="movie_comment",
        cascade="all, delete-orphan",
    )

    @property
    def replies_count(self) -> int:
        return len(self.comment_replies)

    def __repr__(self) -> str:
        return f"UserMovieComment(user_id={self.user_id}, movie_id={self.movie_id}, comment={self.comment})"


class MovieCommentReply(Base):
    __tablename__ = "comment_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_comment_id: Mapped[int] = mapped_column(
        ForeignKey("user_movie_comments.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(String(250), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="comment_replies")
    movie_comment: Mapped["UserMovieComment"] = relationship(
        "UserMovieComment", back_populates="comment_replies"
    )

    def __repr__(self) -> str:
        return (
            f"MovieCommentReply(user_id={self.user_id}, "
            f"movie_comment_id={self.movie_comment_id}, content={self.content})"
        )


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

    movie_reactions: Mapped[list["UserMovieReaction"]] = relationship(
        "UserMovieReaction", back_populates="user", cascade="all, delete-orphan"
    )
    movie_comments: Mapped[list["UserMovieComment"]] = relationship(
        "UserMovieComment", back_populates="user", cascade="all, delete-orphan"
    )
    comment_replies: Mapped[list["MovieCommentReply"]] = relationship(
        "MovieCommentReply", back_populates="user", cascade="all, delete-orphan"
    )
    favorite_movies: Mapped[list["Movie"]] = relationship(
        "Movie", secondary=UserMovieFavoritesModel, back_populates="favorited_by_users"
    )
    movie_ratings: Mapped[list["UserMovieRating"]] = relationship(
        "UserMovieRating", back_populates="user", cascade="all, delete-orphan"
    )

    @classmethod
    def create(cls, email: str, raw_password: str, group_id: int) -> "User":
        """
        Method to simplify the creation of a new User instance.
        It hashes the raw password and sets the necessary attributes.
        """
        user = cls(email=email, group_id=group_id)
        user.password = raw_password
        return user

    @property
    def password(self) -> None:
        raise AttributeError("Password is write-only.")

    @password.setter
    def password(self, raw_password: str) -> None:
        """Set the user's password after checking its strength and hashing it."""

        validate_password_strength(raw_password)
        self._hashed_password = hash_password(raw_password)

    @validates("email")
    def validate_email(self, key, email: str) -> str | None:
        return validate_email(email.lower())

    def verify_password(self, raw_password: str) -> bool:
        return verify_password(raw_password, self._hashed_password)

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


class PasswordResetToken(TokenBase):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (UniqueConstraint("user_id"),)

    user: Mapped["User"] = relationship("User", back_populates="password_reset_token")

    def __repr__(self) -> str:
        return f"PasswordResetToken(user_id={self.user_id}, token={self.token}, expires_at={self.expires_at})"


class RefreshToken(TokenBase):
    __tablename__ = "refresh_tokens"

    user: Mapped["User"] = relationship("User", back_populates="refresh_token")

    @classmethod
    def create(cls, user_id: int, token: str, days_valid: int) -> "RefreshToken":
        """
        Method to simplify the creation of a refresh token.
        Calculates the expiration time using the days_valid argument and sets
        the required attributes.
        """
        expires_at = datetime.now(timezone.utc) + timedelta(days=days_valid)
        return cls(user_id=user_id, token=token, expires_at=expires_at)

    def __repr__(self) -> str:
        return f"RefreshToken(user_id={self.user_id}, token={self.token}), expires_at={self.expires_at}"

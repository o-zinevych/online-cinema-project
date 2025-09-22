from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Integer,
    String,
    Table,
    Column,
    ForeignKey,
    Uuid,
    Float,
    Text,
    DECIMAL,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.accounts import MovieReactionEnum
from database.models.base import Base


MovieGenresModel = Table(
    "movie_genres",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "genre_id",
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
)


MovieStarsModel = Table(
    "movie_stars",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "star_id",
        ForeignKey("stars.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
)


MovieDirectorsModel = Table(
    "movie_directors",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "director_id",
        ForeignKey("directors.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
)


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    movies: Mapped[list["Movie"]] = relationship(
        "Movie", secondary=MovieGenresModel, back_populates="genres"
    )

    def __repr__(self) -> str:
        return f"Genre(name={self.name})"


class Star(Base):
    __tablename__ = "stars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    movies: Mapped[list["Movie"]] = relationship(
        "Movie", secondary=MovieStarsModel, back_populates="stars"
    )

    def __repr__(self) -> str:
        return f"Star(name={self.name})"


class Director(Base):
    __tablename__ = "directors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    movies: Mapped[list["Movie"]] = relationship(
        "Movie", secondary=MovieDirectorsModel, back_populates="directors"
    )

    def __repr__(self) -> str:
        return f"Director(name={self.name})"


class Certification(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    movies: Mapped[list["Movie"]] = relationship(
        "Movie", back_populates="certification"
    )

    def __repr__(self) -> str:
        return f"Certification(name={self.name})"


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False, default=uuid4)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    time: Mapped[int] = mapped_column(Integer, nullable=False)
    imdb: Mapped[float] = mapped_column(Float, nullable=False)
    votes: Mapped[int] = mapped_column(Integer, nullable=False)
    meta_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=True)

    certification_id: Mapped[int] = mapped_column(
        ForeignKey("certifications.id", ondelete="CASCADE"), nullable=False
    )
    certification: Mapped["Certification"] = relationship(
        "Certification", back_populates="movies"
    )

    genres: Mapped[list["Genre"]] = relationship(
        "Genre", secondary=MovieGenresModel, back_populates="movies"
    )
    directors: Mapped[list["Director"]] = relationship(
        "Director", secondary=MovieDirectorsModel, back_populates="movies"
    )
    stars: Mapped[list["Star"]] = relationship(
        "Star", secondary=MovieStarsModel, back_populates="movies"
    )

    user_reactions: Mapped[list["UserMovieReaction"]] = relationship(
        "UserMovieReaction", back_populates="movie", cascade="all, delete-orphan"
    )
    user_comments: Mapped[list["UserMovieComment"]] = relationship(
        "UserMovieComment", back_populates="movie", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "name", "year", "time", name="movie_name_year_time_constraint"
        ),
    )

    @property
    def likes_count(self) -> int:
        return sum(
            1 for r in self.user_reactions if r.reaction == MovieReactionEnum.LIKE
        )

    @property
    def dislikes_count(self) -> int:
        return sum(
            1 for r in self.user_reactions if r.reaction == MovieReactionEnum.DISLIKE
        )

    @property
    def comments_count(self) -> int:
        return len(self.user_comments)

    def __repr__(self) -> str:
        return f"Movie(name={self.name}, year={self.year}, imdb_score={self.imdb})"

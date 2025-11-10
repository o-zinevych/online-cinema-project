from typing import TypeVar, Type, Optional

from fastapi import Depends, HTTPException
from sqlalchemy import select, Select, desc, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from starlette import status

from database import get_db
from database.models import (
    Certification,
    Genre,
    Director,
    Star,
    Movie,
    UserMovieFavoritesModel,
    UserMovieComment,
    MovieCommentReply,
)
from schemas.movies import (
    GenreSchema,
    DirectorSchema,
    StarSchema,
    FilterParams,
    MovieListItemSchema,
)
from services.common_utils import (
    count_total_items,
    apply_limit_offset_to_item_list,
    count_total_pages,
)

TModel = TypeVar("TModel", Genre, Director, Star)

no_movies_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="No movies found."
)
movie_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
)
comment_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found."
)
comment_under_wrong_movie_exception = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="This comment does not belong to this movie.",
)
comment_not_own_exception = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You are not the creator of this comment.",
)
reply_under_wrong_comment_exception = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="This reply does not belong to this comment.",
)
star_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Star not found."
)


async def get_or_create_certification(
    certification_name: str, db: AsyncSession = Depends(get_db)
) -> Certification | None:
    """Retrieves or creates a certification by its name."""
    certification_stmt = select(Certification).where(
        Certification.name == certification_name
    )
    certification_result = await db.execute(certification_stmt)
    certification = certification_result.scalar_one_or_none()
    if certification:
        return certification

    try:
        new_certification = Certification(name=certification_name)
        db.add(new_certification)
        await db.flush()
        return new_certification
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when creating the certification.",
        )


async def get_or_create_related_movie_items(
    item_list: list[GenreSchema | DirectorSchema | StarSchema],
    model: Type[TModel],
    item_type: str,
    db: AsyncSession = Depends(get_db),
) -> list[TModel]:
    """Retrieves the existing items related to a movie or creates them if non-existent."""
    final_items = []
    for item in item_list:
        stmt = select(model).where(model.name.ilike(item.name))
        result = await db.execute(stmt)
        db_item = result.scalar_one_or_none()

        if db_item:
            final_items.append(db_item)
        else:
            try:
                new_item_data = item.model_dump()
                new_item_data["name"] = new_item_data["name"].title()
                new_item = model(**new_item_data)
                db.add(new_item)
                await db.flush()
                final_items.append(new_item)
            except SQLAlchemyError:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An error occurred when creating the {item_type}.",
                )

    return final_items


def apply_movie_filters(stmt, **filters) -> Select:
    """Applies the filters and ordering from the given dictionary to the base query."""
    name = filters.get("name")
    if name:
        stmt = stmt.filter(Movie.name.ilike(f"%{name}%"))

    description = filters.get("description")
    if description:
        stmt = stmt.filter(Movie.description.ilike(f"%{description}%"))

    year = filters.get("year")
    year_to = filters.get("year_to")
    year_from = filters.get("year_from")
    if year:
        stmt = stmt.filter(Movie.year == year)
    elif year_to and year_from:
        stmt = stmt.filter(Movie.year.between(year_from, year_to))
    elif year_to:
        stmt = stmt.filter(Movie.year.__le__(year_to))
    elif year_from:
        stmt = stmt.filter(Movie.year.__ge__(year_from))

    shorter_than = filters.get("shorter_than")
    longer_than = filters.get("longer_than")
    if shorter_than and longer_than:
        stmt = stmt.filter(Movie.time.between(longer_than, shorter_than))
    elif shorter_than:
        stmt = stmt.filter(Movie.time.__le__(shorter_than))
    elif longer_than:
        stmt = stmt.filter(Movie.time.__ge__(longer_than))

    imdb_from = filters.get("imdb_from")
    imdb_to = filters.get("imdb_to")
    if imdb_from and imdb_to:
        stmt = stmt.filter(Movie.imdb.between(imdb_from, imdb_to))
    elif imdb_from:
        stmt = stmt.filter(Movie.imdb.__ge__(imdb_from))
    elif imdb_to:
        stmt = stmt.filter(Movie.imdb.__le__(imdb_to))

    certification = filters.get("certification")
    if certification:
        stmt = stmt.filter(
            Movie.certification.has(Certification.name.ilike(certification))
        )

    genres = filters.get("genres")
    if genres:
        genre_list = [genre.strip() for genre in genres.split(",")]
        for genre in genre_list:
            stmt = stmt.filter(Movie.genres.any(Genre.name.ilike(genre)))

    directors = filters.get("directors")
    if directors:
        director_list = [director.strip() for director in directors.split(",")]
        for director in director_list:
            stmt = stmt.filter(
                Movie.directors.any(Director.name.ilike(f"%{director}%"))
            )

    stars = filters.get("stars")
    if stars:
        star_list = [star.strip() for star in stars.split(",")]
        for star in star_list:
            stmt = stmt.filter(Movie.stars.any(Star.name.ilike(f"%{star}%")))

    order_by = filters.get("order_by")
    if order_by == "id":
        stmt = stmt.order_by(Movie.id)
    elif order_by == "name":
        stmt = stmt.order_by(Movie.name)
    elif order_by == "year":
        stmt = stmt.order_by(desc(Movie.year))
    elif order_by == "imdb":
        stmt = stmt.order_by(desc(Movie.imdb))

    return stmt


def add_filters_to_movie_list_page_links(
    base_url: str, filter_query: FilterParams
) -> str:
    """Adds filters from filter_query where applicable to the page link string."""
    return (
        base_url
        + (f"&name={filter_query.name}" if filter_query.name else "")
        + (
            f"&description={filter_query.description}"
            if filter_query.description
            else ""
        )
        + (f"&year={filter_query.year}" if filter_query.year else "")
        + (
            f"&year_from={filter_query.year_from}"
            if filter_query.year_from and not filter_query.year
            else ""
        )
        + (
            f"&year_to={filter_query.year_to}"
            if filter_query.year_to and not filter_query.year
            else ""
        )
        + (
            f"&longer_than={filter_query.longer_than}"
            if filter_query.longer_than
            else ""
        )
        + (
            f"&shorter_than={filter_query.shorter_than}"
            if filter_query.shorter_than
            else ""
        )
        + (f"&imdb_from={filter_query.imdb_from}" if filter_query.imdb_from else "")
        + (f"&imdb_to={filter_query.imdb_to}" if filter_query.imdb_to else "")
        + (
            f"&certification={filter_query.certification}"
            if filter_query.certification
            else ""
        )
        + (f"&genres={filter_query.genres}" if filter_query.genres else "")
        + (f"&directors={filter_query.directors}" if filter_query.directors else "")
        + (f"&stars={filter_query.stars}" if filter_query.stars else "")
    )


async def get_paginated_movies(
    filter_query: FilterParams,
    base_url: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[int] = None,
) -> dict:
    """
    Get paginated movie list with optional filters, including user favorites.

    Args:
        filter_query (FilterParams): Filters to apply to the movie list.
        base_url (str): Base URL of the API to build the links.
        db (AsyncSession): Asynchronous database session.
        user_id (Optional[int]): The request's user ID.

    Returns:
        dict: The movie list with pagination data and page links.
    """
    stmt = select(Movie).options(
        joinedload(Movie.certification),
        selectinload(Movie.genres),
        selectinload(Movie.directors),
        selectinload(Movie.stars),
    )
    if user_id:
        stmt = stmt.join(UserMovieFavoritesModel).where(
            and_(UserMovieFavoritesModel.c.user_id == user_id)
        )

    filter_params = filter_query.model_dump()
    stmt = apply_movie_filters(stmt, **filter_params)

    total_items = await count_total_items(stmt, db)
    if not total_items:
        raise no_movies_exception

    page = filter_query.page
    per_page = filter_query.per_page
    movie_list = await apply_limit_offset_to_item_list(
        stmt, page, per_page, no_movies_exception, MovieListItemSchema, db
    )
    total_pages = count_total_pages(total_items, per_page)

    prev_page_link = add_filters_to_movie_list_page_links(
        f"{base_url}?page={page - 1}&per_page={per_page}&order_by={filter_query.order_by}",
        filter_query,
    )
    next_page_link = add_filters_to_movie_list_page_links(
        f"{base_url}?page={page + 1}&per_page={per_page}&order_by={filter_query.order_by}",
        filter_query,
    )
    return {
        "movies": movie_list,
        "prev_page": prev_page_link if page > 1 else None,
        "next_page": next_page_link if page < total_pages else None,
        "total_pages": total_pages,
        "total_items": total_items,
    }


def get_movie_by_id_stmt(movie_id: int) -> Select:
    return (
        select(Movie)
        .options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.directors),
            selectinload(Movie.stars),
            selectinload(Movie.user_reactions),
            selectinload(Movie.user_comments),
            selectinload(Movie.favorited_by_users),
            selectinload(Movie.cart_items),
        )
        .where(Movie.id == movie_id)
    )


async def get_and_check_comment(
    stmt: Select,
    movie_id: int,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> UserMovieComment | MovieCommentReply:
    """
    Retrieves and checks a comment's existence and movie ID.
    Checks the owner if user_id is provided.
    """
    comment_result = await db.execute(stmt)
    comment = comment_result.scalar_one_or_none()
    if not comment:
        raise comment_not_found_exception

    if comment.movie_id != movie_id:
        raise comment_under_wrong_movie_exception

    if user_id and comment.user_id != user_id:
        raise comment_not_own_exception
    return comment


async def get_and_check_comment_reply(
    stmt: Select,
    comment_id: int,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> MovieCommentReply:
    """
    Retrieves and checks a reply's existence and comment ID.
    Checks the owner if user_id is provided.
    """
    reply_result = await db.execute(stmt)
    reply = reply_result.scalar_one_or_none()
    if not reply:
        raise comment_not_found_exception

    if reply.movie_comment_id != comment_id:
        raise reply_under_wrong_comment_exception

    if user_id and reply.user_id != user_id:
        raise comment_not_own_exception

    return reply


async def get_star_by_id_or_raise(
    star_id: int, db: AsyncSession = Depends(get_db)
) -> Star:
    stmt = select(Star).where(Star.id == star_id)
    result = await db.execute(stmt)
    star = result.scalar_one_or_none()
    if not star:
        raise star_not_found_exception
    return star

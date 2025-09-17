from typing import Annotated

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func, Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from starlette import status

from database import get_db
from database.models.accounts import User
from database.models.movies import Movie, Certification
from schemas.movies import MovieListResponseSchema, MovieListItemSchema, FilterParams
from security.account_utils import get_current_user

router = APIRouter()


def apply_movie_filters(stmt, **filters) -> Select:
    """Applies the filters from the given dictionary to the base query."""
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

    return stmt


@router.get(
    "/movies/",
    response_model=MovieListResponseSchema,
    summary="Movie List",
    description="Get the list of movies with pagination.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not found - No movies found.",
            "content": {
                "application/json": {"example": {"detail": "No movies found."}}
            },
        },
    },
)
async def get_movies(
    filter_query: Annotated[FilterParams, Query()],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MovieListResponseSchema:
    """
    Movie list endpoint.

    Retrieves the list of movies allowing the client to specify the page number and
    the number of items per page. It also calculates the total number of pages and items.
    Provides the links to previous and next pages when applicable.
    The list can be filtered and searched by the required movie fields.

    Args:
        filter_query: The filters to apply to the query.
        db (AsyncSession): Asynchronous database session.
        current_user (User): The authenticated user.

    Returns:
        MovieListResponseSchema: Movie list response.

    Raises:
        HTTPException:
            - 404 if no movies are found.
    """
    no_movies_exception = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No movies found."
    )

    page = filter_query.page
    per_page = filter_query.per_page

    stmt = select(Movie).options(joinedload(Movie.certification))
    filter_params = filter_query.model_dump()
    stmt = apply_movie_filters(stmt, **filter_params)

    count_stmt = select(func.count()).select_from(stmt.alias())
    count_result = await db.execute(count_stmt)
    total_items = count_result.scalar() or 0
    if not total_items:
        raise no_movies_exception

    offset = (page - 1) * per_page
    stmt = stmt.limit(per_page).offset(offset)
    movie_result = await db.execute(stmt)
    movies = movie_result.scalars().all()
    if not movies:
        raise no_movies_exception

    movie_list = [MovieListItemSchema.model_validate(movie) for movie in movies]
    total_pages = (total_items + per_page - 1) // per_page
    return MovieListResponseSchema(
        movies=movie_list,
        prev_page=(
            f"/cinema/movies/?page={page - 1}&per_page={per_page}"
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
            + (f"imdb_from={filter_query.imdb_from}" if filter_query.imdb_from else "")
            + (f"imdb_to={filter_query.imdb_to}" if filter_query.imdb_to else "")
            + (
                f"certification={filter_query.certification}"
                if filter_query.certification
                else ""
            )
            if page > 1
            else None
        ),
        next_page=(
            f"/cinema/movies/?page={page + 1}&per_page={per_page}"
            + (f"&name={filter_query.name}" if filter_query.name else "")
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
            + (f"imdb_from={filter_query.imdb_from}" if filter_query.imdb_from else "")
            + (f"imdb_to={filter_query.imdb_to}" if filter_query.imdb_to else "")
            + (
                f"certification={filter_query.certification}"
                if filter_query.certification
                else ""
            )
            if page < total_pages
            else None
        ),
        total_pages=total_pages,
        total_items=total_items,
    )

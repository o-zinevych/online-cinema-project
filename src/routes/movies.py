from typing import Annotated

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from database import get_db
from database.models.accounts import User
from database.models.movies import Movie
from schemas.movies import MovieListResponseSchema, MovieListItemSchema, FilterParams
from security.account_utils import get_current_user

router = APIRouter()


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
    The list can be filtered and searched by all the movie fields.

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
    count_result = await db.execute(select(func.count(Movie.id)))
    total_items = count_result.scalar() or 0
    if not total_items:
        raise no_movies_exception

    page = filter_query.page
    per_page = filter_query.per_page

    stmt = select(Movie)
    name = filter_query.name
    if name:
        stmt = stmt.filter(Movie.name.ilike(f"%{name}%"))

    year = filter_query.year
    year_to = filter_query.year_to
    year_from = filter_query.year_from
    if year:
        stmt = stmt.filter(Movie.year == year)
    if year_to:
        stmt = stmt.filter(Movie.year.__le__(year_to))
    if year_from:
        stmt = stmt.filter(Movie.year.__ge__(year_from))

    shorter_than = filter_query.shorter_than
    longer_than = filter_query.longer_than
    if shorter_than and longer_than:
        stmt = stmt.filter(Movie.time.between(longer_than, shorter_than))
    elif shorter_than:
        stmt = stmt.filter(Movie.time.__le__(shorter_than))
    elif longer_than:
        stmt = stmt.filter(Movie.time.__ge__(longer_than))

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
            f"/cinema/movies/?page={page - 1}&per_page={per_page}" if page > 1 else None
        ),
        next_page=(
            f"/cinema/movies/?page={page + 1}&per_page={per_page}"
            if page < total_pages
            else None
        ),
        total_pages=total_pages,
        total_items=total_items,
    )

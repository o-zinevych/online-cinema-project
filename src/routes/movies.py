from typing import Annotated

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func, Select, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from starlette import status

from database import get_db
from database.models.accounts import (
    User,
    UserMovieReaction,
    MovieReactionEnum,
    UserMovieComment,
)
from database.models.movies import Movie, Certification, Genre, Director, Star
from schemas.common import MessageResponseSchema
from schemas.movies import (
    MovieListResponseSchema,
    MovieListItemSchema,
    FilterParams,
    MovieDetailSchema,
    MovieReactionRequestSchema,
    CommentCreateResponseSchema,
    CommentCreateSchema,
)
from security.account_utils import get_current_user

router = APIRouter()

no_movies_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="No movies found."
)
movie_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
)


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
        )
        .where(Movie.id == movie_id)
    )


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
    The list is sorted by id by default, but the client can sort it by the name,
    year and score.

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

    page = filter_query.page
    per_page = filter_query.per_page

    stmt = select(Movie).options(
        joinedload(Movie.certification),
        selectinload(Movie.genres),
        selectinload(Movie.directors),
        selectinload(Movie.stars),
    )
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
            f"/cinema/movies/?page={page - 1}&per_page={per_page}&order_by={filter_query.order_by}"
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
            + (f"genres={filter_query.genres}" if filter_query.genres else "")
            + (f"directors={filter_query.directors}" if filter_query.directors else "")
            + (f"stars={filter_query.stars}" if filter_query.stars else "")
            if page > 1
            else None
        ),
        next_page=(
            f"/cinema/movies/?page={page + 1}&per_page={per_page}&order_by={filter_query.order_by}"
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
            + (f"genres={filter_query.genres}" if filter_query.genres else "")
            + (f"directors={filter_query.directors}" if filter_query.directors else "")
            + (f"stars={filter_query.stars}" if filter_query.stars else "")
            if page < total_pages
            else None
        ),
        total_pages=total_pages,
        total_items=total_items,
    )


@router.get(
    "/movies/{movie_id}/",
    response_model=MovieDetailSchema,
    summary="Movie Detail",
    description="Get movie details by movie id.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        }
    },
)
async def get_movie_by_id(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MovieDetailSchema:
    """
    Movie detail endpoint.

    Retrieves the movie by the given id, including all its details.

    Args:
        movie_id (int): ID of the movie to retrieve.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MovieDetailResponseSchema: Movie detail response.

    Raises:
        HTTPException:
            - 404 if the movie with the given ID was not found.
    """
    stmt = get_movie_by_id_stmt(movie_id)
    result = await db.execute(stmt)
    movie_record = result.scalar_one_or_none()
    if not movie_record:
        raise movie_not_found_exception
    return MovieDetailSchema.model_validate(movie_record)


@router.post(
    "/movies/{movie_id}/react/",
    response_model=MessageResponseSchema,
    summary="Leave a Movie Reaction",
    description="Leave a like or dislike on a movie.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request- The same reaction already exists.",
            "content": {
                "application/json": {
                    "example": {"detail": "You cannot leave the same reaction twice."}
                }
            },
        },
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred when updating/creating a reaction.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when leaving a reaction."}
                }
            },
        },
    },
)
async def leave_movie_reaction(
    movie_id: int,
    reaction_data: MovieReactionRequestSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Movie reaction endpoint.

    Allows users to leave a reaction (like or dislike) on the specified movie.
    Raises an error if the same reaction exists already and changes it if it is different.

    Args:
        movie_id (int): ID of the movie to react to.
        reaction_data (MovieReactionRequestSchema): Information about the reaction.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message about successful reaction creation/update.

    Raises:
        HTTPException:
            - 400 if the user tries to leave the same reaction again.
            - 404 if the movie with the given ID was not found.
            - 500 if an error occurred when updating or creating a reaction.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    reaction_stmt = select(UserMovieReaction).where(
        UserMovieReaction.movie_id == movie_id,
        UserMovieReaction.user_id == current_user.id,
    )
    reaction_result = await db.execute(reaction_stmt)
    db_reaction = reaction_result.scalar_one_or_none()
    user_reaction = reaction_data.reaction
    if db_reaction and db_reaction.reaction == user_reaction:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot leave the same reaction twice.",
        )

    reaction_db_exception = HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An error occurred when leaving a reaction.",
    )

    if db_reaction and db_reaction.reaction != user_reaction:
        try:
            db_reaction.reaction = user_reaction
            await db.commit()
            if user_reaction == MovieReactionEnum.LIKE:
                return MessageResponseSchema(message="Movie liked successfully.")
            return MessageResponseSchema(message="Movie disliked successfully.")
        except SQLAlchemyError:
            await db.rollback()
            raise reaction_db_exception

    try:
        new_reaction = UserMovieReaction(
            user_id=current_user.id, movie_id=movie_id, reaction=user_reaction
        )
        db.add(new_reaction)
        await db.flush()
        await db.commit()
        await db.refresh(new_reaction)
        if user_reaction == MovieReactionEnum.LIKE:
            return MessageResponseSchema(message="Movie liked successfully.")
        return MessageResponseSchema(message="Movie disliked successfully.")
    except SQLAlchemyError:
        await db.rollback()
        raise reaction_db_exception


@router.post(
    "/movies/{movie_id}/comments/",
    response_model=CommentCreateResponseSchema,
    summary="Create a Comment",
    description="Create a comment under a specific movie.",
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during comment creation.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred when creating the comment."
                    }
                }
            },
        },
    },
)
async def create_comment(
    movie_id: int,
    comment_data: CommentCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentCreateResponseSchema:
    """
    Comment creation endpoint.

    Creates a comment under 250 characters by current user for the given movie.

    Args:
        movie_id (int): ID of the movie to comment on.
        comment_data (CommentCreateSchema): The user's comment.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CommentCreateResponseSchema: Comment details including its ID, comment itself,
        the user ID and time of creation.

    Raises:
        HTTPException:
            - 404 if the movie with the given ID was not found.
            - 500 if an error occurred during comment creation.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    try:
        new_comment = UserMovieComment(
            user_id=current_user.id, movie_id=movie_id, comment=comment_data.comment
        )
        db.add(new_comment)
        await db.commit()
        await db.refresh(new_comment)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when creating the comment.",
        )
    return CommentCreateResponseSchema.model_validate(new_comment)

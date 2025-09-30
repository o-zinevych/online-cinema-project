from typing import Annotated, Optional, TypeVar, Type

from fastapi import APIRouter, Query, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, func, Select, desc, and_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from starlette import status

from config.dependencies import get_account_email_sender, get_settings
from database import get_db
from database.models.accounts import (
    User,
    UserMovieReaction,
    ReactionEnum,
    UserMovieComment,
    UserMovieFavoritesModel,
    UserMovieRating,
    MovieCommentReply,
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
    CommentUpdateResponseSchema,
    CommentUpdateSchema,
    CommentListResponseSchema,
    CommentListItemSchema,
    FavoriteMovieListResponseSchema,
    GenreListResponseSchema,
    GenreListItemSchema,
    MovieRatingRequestSchema,
    CommentReplyCreateResponseSchema,
    CommentReplyCreateSchema,
    CommentReplyListResponseSchema,
    CommentReplyListItemSchema,
    CommentReplyUpdateResponseSchema,
    CommentReplyUpdateSchema,
    MovieCreateResponseSchema,
    MovieCreateRequestSchema,
    GenreSchema,
    DirectorSchema,
    StarSchema,
    MovieUpdateRequestSchema,
)
from security.account_utils import get_current_user, require_moderator_or_admin

router = APIRouter()

base_email_url = "http://127.0.0.1:8000/api/v1/cinema"
email_sender = get_account_email_sender(get_settings())

no_movies_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="No movies found."
)
movie_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
)

comment_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found."
)
no_comments_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="No comments found."
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

T = TypeVar("T", Genre, Director, Star)


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
    model: Type[T],
    item_type: str,
    db: AsyncSession = Depends(get_db),
) -> list[T]:
    """Retrieves the existing items related to a movie or creates them if non-existent."""
    final_items = []
    for item in item_list:
        stmt = select(model).where(model.name == item.name)
        result = await db.execute(stmt)
        db_item = result.scalar_one_or_none()

        if db_item:
            final_items.append(db_item)
        else:
            try:
                new_item_data = item.model_dump()
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


def count_offset(page: int, per_page: int) -> int:
    """Counts the offset for pagination based on current page and per_page."""
    return (page - 1) * per_page


def count_total_pages(total_items: int, per_page: int) -> int:
    """Counts the total pages number for pagination based on items total and per_page."""
    return (total_items + per_page - 1) // per_page


async def count_total_items(stmt: Select, db: AsyncSession = Depends(get_db)) -> int:
    """Counts the total amount of items."""
    count_stmt = select(func.count()).select_from(stmt.alias())
    count_result = await db.execute(count_stmt)
    total_items = count_result.scalar() or 0
    return total_items


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


async def apply_limit_offset_to_movie_list(
    stmt: Select, page: int, per_page: int, db: AsyncSession = Depends(get_db)
):
    """
    Applies the given limit and offset to the statement, executes it
    and returns the movie list.
    """
    offset = count_offset(page, per_page)
    stmt = stmt.limit(per_page).offset(offset)
    result = await db.execute(stmt)
    movies = result.scalars().all()
    if not movies:
        raise no_movies_exception
    movie_list = [MovieListItemSchema.model_validate(movie) for movie in movies]
    return movie_list


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
    movie_list = await apply_limit_offset_to_movie_list(stmt, page, per_page, db)
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


@router.post(
    "/movies/",
    response_model=MovieCreateResponseSchema,
    summary="Create a Movie",
    description="Create a movie if moderator or admin.",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "description": "Bad Request - Invalid data to create movie was provided.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid data: A constraint was violated."}
                }
            },
        },
        403: {
            "description": "Forbidden - Only moderator or admin can perform this action.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You must be a moderator or admin to do this."
                    }
                }
            },
        },
        409: {
            "description": "Conflict - Movie name, year and runtime constraint violated.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "A movie with this name, year, and runtime already exists."
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during movie "
            "or its elements creation.",
            "content": {
                "application/json": {
                    "examples": {
                        "movie_db_error": {
                            "summary": "Movie Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the movie."
                            },
                        },
                        "certification_db_error": {
                            "summary": "Certification Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the certification."
                            },
                        },
                        "genre_db_error": {
                            "summary": "Genre Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the genre."
                            },
                        },
                        "director_db_error": {
                            "summary": "Director Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the director."
                            },
                        },
                        "star_db_error": {
                            "summary": "Star Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the star."
                            },
                        },
                    }
                }
            },
        },
    },
)
async def create_movie(
    movie_data: MovieCreateRequestSchema,
    current_user: User = Depends(require_moderator_or_admin),
    db: AsyncSession = Depends(get_db),
) -> MovieCreateResponseSchema:
    """
    Movie creation endpoint.

    Allows moderators and admin users to create a new movie instance.
    Handles Integrity and SQLAlchemy errors in the process of creation.
    If the certificate, genres, directors or stars do not exist in the database,
    they will be created.

    Args:
        movie_data (MovieCreateRequestSchema): The information about the movie.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MovieCreateResponseSchema: The details of the created movie.

    Raises:
        HTTPException:
            - 400 if the provided data is invalid, a constraint was violated.
            - 403 if the user is not a moderator or admin.
            - 409 if the unique constraint on name, year and runtime was violated.
            - 500 if an error occurred during movie or its elements' creation.
    """
    try:
        certification = await get_or_create_certification(
            movie_data.certification.name, db
        )
        certification_id = certification.id

        genres = await get_or_create_related_movie_items(
            item_list=movie_data.genres, model=Genre, item_type="genre", db=db
        )

        directors = await get_or_create_related_movie_items(
            item_list=movie_data.directors, model=Director, item_type="director", db=db
        )

        stars = await get_or_create_related_movie_items(
            item_list=movie_data.stars, model=Star, item_type="star", db=db
        )

        base_movie_data = movie_data.model_dump(
            exclude={"certification", "genres", "directors", "stars"}
        )
        new_movie = Movie(**base_movie_data)
        new_movie.certification_id = certification_id

        new_movie.genres = genres
        new_movie.directors = directors
        new_movie.stars = stars

        db.add(new_movie)
        await db.flush()
        await db.commit()

        return MovieCreateResponseSchema.model_validate(new_movie)
    except IntegrityError as error:
        await db.rollback()
        if "movie_name_year_time_constraint" in str(error):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A movie with this name, year, and runtime already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid data: A constraint was violated.",
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when creating the movie.",
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
    result = await get_paginated_movies(
        filter_query=filter_query, base_url="/cinema/movies/", db=db
    )
    return MovieListResponseSchema(**result)


@router.get(
    "/movies/my-favorites/",
    response_model=FavoriteMovieListResponseSchema,
    summary="Favorite Movies List",
    description="Get a paginated list of favorite movies with optional"
    "sorting and filtering.",
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
async def get_favorite_movies(
    filter_query: Annotated[FilterParams, Query()],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FavoriteMovieListResponseSchema:
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
    result = await get_paginated_movies(
        filter_query=filter_query,
        base_url="/cinema/movies/my-favorites/",
        db=db,
        user_id=current_user.id,
    )
    return FavoriteMovieListResponseSchema(**result)


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


@router.patch(
    "/movies/{movie_id}/",
    response_model=MovieDetailSchema,
    summary="Movie Update",
    description="Update movie data if moderator or admin.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Invalid update data.",
            "content": {
                "application/json": {
                    "examples": {
                        "no_update_data": {
                            "summary": "No Data Provided",
                            "value": {"detail": "No update data was provided."},
                        },
                        "invalid_data": {
                            "summary": "Invalid Data Provided",
                            "value": {
                                "detail": "Invalid data: A constraint was violated."
                            },
                        },
                    }
                }
            },
        },
        403: {
            "description": "Forbidden - Only moderator or admin can perform this action.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You must be a moderator or admin to do this."
                    }
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
            "description": "Internal Server Error - An error occurred during movie update"
            " or its elements creation.",
            "content": {
                "application/json": {
                    "examples": {
                        "movie_db_error": {
                            "summary": "Movie Update Error",
                            "value": {
                                "detail": "An error occurred when updating the movie."
                            },
                        },
                        "certification_db_error": {
                            "summary": "Certification Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the certification."
                            },
                        },
                        "genre_db_error": {
                            "summary": "Genre Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the genre."
                            },
                        },
                        "director_db_error": {
                            "summary": "Director Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the director."
                            },
                        },
                        "star_db_error": {
                            "summary": "Star Creation Error",
                            "value": {
                                "detail": "An error occurred when creating the star."
                            },
                        },
                    }
                }
            },
        },
    },
)
async def update_movie(
    movie_id: int,
    update_data: MovieUpdateRequestSchema,
    current_user: User = Depends(require_moderator_or_admin),
    db: AsyncSession = Depends(get_db),
) -> MovieDetailSchema:
    """
    Movie update endpoint.

    Allows moderators and admin users to partially update the movie data.
    If the related certificate, genres, directors or stars do not exist in the database,
    they will be created.

    Args:
        movie_id (int): ID of the movie to update.
        update_data (MovieUpdateRequestSchema): Data to update in the movie.
        current_user (User): The current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MovieDetailSchema: Movie detail response with all the movie data.

    Raises:
        HTTPException:
            - 400 if the provided data is invalid, a constraint was violated.
            - 403 if the user is not a moderator or admin.
            - 404 if the movie with the given ID was not found.
            - 500 if an error occurred during movie update or its elements' creation.
    """
    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data was provided.",
        )

    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie_to_update = movie_result.scalar_one_or_none()
    if not movie_to_update:
        raise movie_not_found_exception

    try:
        update_dict = update_data.model_dump(
            exclude_unset=True,
            exclude={"certification", "genres", "directors", "stars"},
        )
        for field, value in update_dict.items():
            if hasattr(movie_to_update, field):
                setattr(movie_to_update, field, value)

        certification_data = update_data.certification
        if certification_data:
            certification = await get_or_create_certification(
                certification_data.name, db
            )
            movie_to_update.certification_id = certification.id

        genres_data = update_data.genres
        if genres_data:
            genres = await get_or_create_related_movie_items(
                item_list=genres_data, model=Genre, item_type="genre", db=db
            )
            movie_to_update.genres = genres

        directors_data = update_data.directors
        if directors_data:
            directors = await get_or_create_related_movie_items(
                item_list=directors_data, model=Director, item_type="director", db=db
            )
            movie_to_update.directors = directors

        stars_data = update_data.stars
        if stars_data:
            stars = await get_or_create_related_movie_items(
                item_list=stars_data, model=Star, item_type="star", db=db
            )
            movie_to_update.stars = stars

        db.add(movie_to_update)
        await db.flush()
        await db.commit()
        return MovieDetailSchema.model_validate(movie_to_update)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid data: A constraint was violated.",
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when updating the movie.",
        )


@router.post(
    "/movies/{movie_id}/favorite/",
    response_model=MessageResponseSchema,
    summary="Add Movie to Favorites",
    description="Add the specified movie to the list of favorites.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - The movie is already in favorites list.",
            "content": {
                "application/json": {"example": {"detail": "Movie already favorite."}}
            },
        },
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during addition "
            "of the movie to favorites.",
            "content": {
                "application/json": {
                    "examples": {
                        "detail": "An error occurred when adding the movie to favorites."
                    }
                }
            },
        },
    },
)
async def add_movie_to_favorites(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Favorite movie addition endpoint.

    Marks the given movie as favorite provided it is not favorite yet.
    Checks the user's favorite movies list to verify that.

    Args:
        movie_id (int): ID of the movie to make favorite.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message informing the client of successful
        addition of the movie to favorites.

    Raises:
        HTTPException:
            - 400 if the movie is already favorite.
            - 404 if the movie with the given ID was not found.
            - 500 if an error occurred during addition of the movie to favorites.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    if current_user in movie.favorited_by_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Movie already favorite."
        )

    try:
        movie.favorited_by_users.append(current_user)
        await db.commit()
        return MessageResponseSchema(message="Movie added to favorites successfully.")
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when adding the movie to favorites.",
        )


@router.delete(
    "/movies/{movie_id}/favorite/",
    response_model=MessageResponseSchema,
    summary="Remove Movie from Favorites",
    description="Remove the specified movie from the list of favorites.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - The movie is not in favorites list.",
            "content": {
                "application/json": {"example": {"detail": "Movie not favorite."}}
            },
        },
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during removal "
            "of the movie from favorites.",
            "content": {
                "application/json": {
                    "examples": {
                        "detail": "An error occurred when removing the movie from favorites."
                    }
                }
            },
        },
    },
)
async def remove_movie_from_favorites(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Favorite movie removal endpoint.

    Deletes the given movie from the list of favorites.

    Args:
        movie_id (int): ID of the movie to remove from favorites.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Raises:
        HTTPException:
            - 400 if the movie is not favorite.
            - 404 if the movie with the given ID was not found.
            - 500 if an error occurred during removal of the movie from favorites.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    if current_user not in movie.favorited_by_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Movie not favorite."
        )

    try:
        movie.favorited_by_users.remove(current_user)
        await db.commit()
        return MessageResponseSchema(
            message="Movie removed from favorites successfully."
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when removing the movie from favorites.",
        )


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
            if user_reaction == ReactionEnum.LIKE:
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
        if user_reaction == ReactionEnum.LIKE:
            return MessageResponseSchema(message="Movie liked successfully.")
        return MessageResponseSchema(message="Movie disliked successfully.")
    except SQLAlchemyError:
        await db.rollback()
        raise reaction_db_exception


@router.post(
    "/movies/{movie_id}/rate",
    response_model=MessageResponseSchema,
    summary="Rate a Movie",
    description="Give the specified movie a rating from 1 to 10.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred when giving the rating.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when rating the movie."}
                }
            },
        },
    },
)
async def rate_movie(
    movie_id: int,
    rating_data: MovieRatingRequestSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Movie rating endpoint.

    Allows the user to leave a rating from 1 to 10 on the given movie.

    Args:
        movie_id (int): ID of the movie to rate.
        rating_data (MovieRatingRequestSchema): Information about the rating.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message about successful rating creation.

    Raises:
        HTTPException:
            - 404 if the movie with the given ID was not found.
            - 500 if an error occurred during rating creation/update.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    rating_stmt = select(UserMovieRating).where(
        UserMovieRating.movie_id == movie_id, UserMovieRating.user_id == current_user.id
    )
    rating_result = await db.execute(rating_stmt)
    rating_record = rating_result.scalar_one_or_none()

    try:
        rating_to_give = rating_data.rating
        if rating_record:
            rating_record.rating = rating_to_give
        else:
            new_rating = UserMovieRating(
                user_id=current_user.id, movie_id=movie_id, rating=rating_to_give
            )
            db.add(new_rating)
        await db.commit()
        return MessageResponseSchema(
            message=f"You've rated this movie {rating_to_give} out of 10."
        )
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when rating the movie.",
        )


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


@router.get(
    "/movies/{movie_id}/comments/",
    response_model=CommentListResponseSchema,
    summary="Movie Comment List",
    description="Get a paginated list of comments for a specific movie.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {
                    "examples": {
                        "movie_not_found": {
                            "summary": "Movie Not Found",
                            "value": {"detail": "Movie not found."},
                        },
                        "comments_not_found": {
                            "summary": "Comments Not Found",
                            "value": {"detail": "No comments found."},
                        },
                    }
                },
            },
        },
    },
)
async def get_comments(
    movie_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(5, ge=1, le=10),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentListResponseSchema:
    """
    Comment list endpoint.

    Retrieves a list of comments for a specific movie with pagination.
    The client can specify a page number and the amount of comments per page in query.

    Args:
        movie_id (int): ID of the movie to retrieve comments for.
        page (int): Page number from the query.
        per_page (int): Number of comments per page.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CommentListResponseSchema: List of comments for a specific movie.

    Raises:
        HTTPException:
            - 404 if the movie with the given ID or comments were not found.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    total_items = movie.comments_count
    if not total_items:
        raise no_comments_exception

    offset = count_offset(page, per_page)
    comment_stmt = (
        select(UserMovieComment)
        .options(selectinload(UserMovieComment.likes))
        .limit(per_page)
        .offset(offset)
    )
    comment_result = await db.execute(comment_stmt)
    comments = comment_result.scalars().all()
    if not comments:
        raise no_comments_exception

    comment_list = [
        CommentListItemSchema.model_validate(comment) for comment in comments
    ]
    total_pages = count_total_pages(total_items, per_page)
    return CommentListResponseSchema(
        comments=comment_list,
        prev_page=(
            f"/cinema/movies/{movie_id}/comments/?page={page - 1}&per_page={per_page}"
            if page > 1
            else None
        ),
        next_page=(
            f"/cinema/movies/{movie_id}/comments/?page={page + 1}&per_page={per_page}"
            if page < total_pages
            else None
        ),
        total_pages=total_pages,
        total_items=total_items,
    )


@router.put(
    "/movies/{movie_id}/comments/{comment_id}/",
    response_model=CommentUpdateResponseSchema,
    summary="Update a Comment",
    description="Update your comment under a specific movie.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Comment does not match the movie.",
            "content": {
                "application/json": {
                    "example": {"detail": "This comment does not belong to this movie."}
                }
            },
        },
        403: {
            "description": "Forbidden - User is not the owner of the comment.",
            "content": {
                "application/json": {
                    "example": {"detail": "You are not the creator of this comment."}
                }
            },
        },
        404: {
            "description": "Not Found - Comment with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Comment not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during comment update.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred when updating the comment."
                    }
                }
            },
        },
    },
)
async def update_own_comment(
    movie_id: int,
    comment_id: int,
    comment_update: CommentUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentUpdateResponseSchema:
    """
    Comment update endpoint.

    Updates current user's comment by given comment and movie ID.
    Checks that the current user is the comment's creator and raises
    an HTTP 403 error if not.

    Args:
        movie_id (int): ID of the movie that was commented on.
        comment_id (int): ID of the comment to update.
        comment_update (CommentUpdateSchema): The user's updated comment.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CommentUpdateResponseSchema: Comment details including its ID, comment itself,
        the user ID and time of update.

    Raises:
        HTTPException:
            - 400 if the comment is not under the given movie.
            - 403 if the comment does not belong to the user.
            - 404 if the comment was not found.
            - 500 if an error occurred during comment update.
    """
    comment_stmt = select(UserMovieComment).where(UserMovieComment.id == comment_id)
    comment_to_update = await get_and_check_comment(
        stmt=comment_stmt, movie_id=movie_id, user_id=current_user.id, db=db
    )

    try:
        comment_to_update.comment = comment_update.comment
        await db.flush()
        await db.commit()
        await db.refresh(comment_to_update)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when updating the comment.",
        )
    return CommentUpdateResponseSchema.model_validate(comment_to_update)


@router.delete(
    "/movies/{movie_id}/comments/{comment_id}/",
    summary="Delete a Comment",
    description="Delete your comment by given ID.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {
            "description": "Bad Request - Comment does not match the movie.",
            "content": {
                "application/json": {
                    "example": {"detail": "This comment does not belong to this movie."}
                }
            },
        },
        403: {
            "description": "Forbidden - User is not the owner of the comment.",
            "content": {
                "application/json": {
                    "example": {"detail": "You are not the creator of this comment."}
                }
            },
        },
        404: {
            "description": "Not Found - Comment with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Comment not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during comment deletion.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred when deleting the comment."
                    }
                }
            },
        },
    },
)
async def delete_own_comment(
    movie_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Comment deletion endpoint.

    Deletes a comment with the given ID after checking that the current user is
    the owner of the comment and it is under the right movie.

    Args:
        movie_id (int): ID of the movie that was commented on.
        comment_id (int): ID of the comment to delete.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Raises:
        HTTPException:
            - 400 if the comment is not under the given movie.
            - 403 if the comment does not belong to the user.
            - 404 if the comment was not found.
            - 500 if an error occurred during comment deletion.
    """
    comment_stmt = select(UserMovieComment).where(UserMovieComment.id == comment_id)
    comment_to_delete = await get_and_check_comment(
        stmt=comment_stmt, movie_id=movie_id, user_id=current_user.id, db=db
    )

    try:
        await db.delete(comment_to_delete)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when deleting the comment.",
        )


@router.post(
    "/movies/{movie_id}/comments/{comment_id}/like/",
    response_model=MessageResponseSchema,
    summary="Like a Comment",
    description="Add or remove your like on a comment.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Comment does not match the movie.",
            "content": {
                "application/json": {
                    "example": {"detail": "This comment does not belong to this movie."}
                }
            },
        },
        404: {
            "description": "Not Found - Comment with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Comment not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred when liking the comment.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when liking the comment."}
                }
            },
        },
    },
)
async def like_comment(
    movie_id: int,
    comment_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Comment like endpoint.

    If the user has not liked this comment yet, adds a like.
    Otherwise, removes the existing like.

    Args:
        movie_id (int): ID of the movie that was commented on.
        comment_id (int): ID of the comment to like.
        background_tasks (BackgroundTasks): Background tasks to send a like notification email.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MessageResponseSchema: Message informing of the successful liking of the comment.

    Raises:
        HTTPException:
            - 400 if the comment is not under the given movie.
            - 404 if the comment was not found.
            - 500 if an error occurred while liking the comment.
    """
    comment_stmt = (
        select(UserMovieComment)
        .options(
            joinedload(UserMovieComment.user), selectinload(UserMovieComment.likes)
        )
        .where(UserMovieComment.id == comment_id)
    )
    comment = await get_and_check_comment(stmt=comment_stmt, movie_id=movie_id, db=db)

    try:
        if current_user in comment.likes:
            comment.likes.remove(current_user)
            await db.commit()
            return MessageResponseSchema(message="Your like successfully removed.")

        comment_link = f"{base_email_url}/movies/{movie_id}/comments/"
        background_tasks.add_task(
            email_sender.send_comment_received_like_email,
            comment.user.email,
            comment_link,
        )

        comment.likes.append(current_user)
        await db.commit()
        return MessageResponseSchema(message="Comment liked successfully.")
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when liking the comment.",
        )


@router.post(
    "/movies/{movie_id}/comments/{comment_id}/replies/",
    response_model=CommentReplyCreateResponseSchema,
    summary="Reply to a Comment",
    description="Reply to the comment with the given ID.",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "description": "Bad Request - Comment does not match the movie.",
            "content": {
                "application/json": {
                    "example": {"detail": "This comment does not belong to this movie."}
                }
            },
        },
        404: {
            "description": "Not Found - Comment with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Comment not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during "
            "comment reply creation.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred when replying to the comment."
                    }
                }
            },
        },
    },
)
async def reply_to_comment(
    movie_id: int,
    comment_id: int,
    reply_data: CommentReplyCreateSchema,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentReplyCreateResponseSchema:
    """
    Comment reply creation endpoint.

    Retrieves the comment to reply to and creates the reply with the given content
    and belonging to the current user.

    Args:
        movie_id (int): ID of the movie that was commented on.
        comment_id (int): ID of the comment to reply to.
        reply_data (CommentReplyCreateSchema): The reply content.
        background_tasks (BackgroundTasks): Background tasks to send new reply notification
        to the comment's owner.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CommentReplyCreateResponseSchema: The reply ID, content, user ID
        and time of creation.

    Raises:
        HTTPException:
            - 400 if the comment is not under the given movie.
            - 404 if the comment was not found.
            - 500 if an error occurred during comment reply creation.
    """
    comment_stmt = (
        select(UserMovieComment)
        .options(joinedload(UserMovieComment.user))
        .where(UserMovieComment.id == comment_id)
    )
    comment = await get_and_check_comment(stmt=comment_stmt, movie_id=movie_id, db=db)

    replies_link = f"{base_email_url}/movies/{movie_id}/comments/{comment_id}/replies/"
    background_tasks.add_task(
        email_sender.send_comment_received_reply_email, comment.user.email, replies_link
    )

    try:
        comment_reply = MovieCommentReply(
            user_id=current_user.id,
            movie_comment_id=comment.id,
            content=reply_data.content,
        )
        db.add(comment_reply)
        await db.commit()
        await db.refresh(comment_reply)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when replying to the comment.",
        )
    return CommentReplyCreateResponseSchema.model_validate(comment_reply)


@router.get(
    "/movies/{movie_id}/comments/{comment_id}/replies/",
    response_model=CommentReplyListResponseSchema,
    summary="Movie Comment Replies List",
    description="Get a list of replies to the specified movie comment.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Comment does not match the movie.",
            "content": {
                "application/json": {
                    "example": {"detail": "This comment does not belong to this movie."}
                }
            },
        },
        404: {
            "description": "Not Found - Movie with the given id not found.",
            "content": {
                "application/json": {
                    "examples": {
                        "movie_not_found": {
                            "summary": "Movie Not Found",
                            "value": {"detail": "Movie not found."},
                        },
                        "comments_not_found": {
                            "summary": "Comments Not Found",
                            "value": {"detail": "No comments found."},
                        },
                    }
                },
            },
        },
    },
)
async def get_comment_replies(
    movie_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentReplyListResponseSchema:
    """
    Comment replies list endpoint.

    Retrieves a list of replies to the specified comment wit total reply count.

    Args:
        movie_id (int): ID of the movie that the comment belongs to.
        comment_id (int): ID of the comment to retrieve replies for.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CommentReplyListResponseSchema: List of replies for a specific comment.

    Raises:
        HTTPException:
            - 400 if the comment is not under the given movie.
            - 404 if the movie with the given ID or comments/replies were not found.
    """
    movie_stmt = get_movie_by_id_stmt(movie_id)
    movie_result = await db.execute(movie_stmt)
    movie = movie_result.scalar_one_or_none()
    if not movie:
        raise movie_not_found_exception

    comment_stmt = (
        select(UserMovieComment)
        .options(selectinload(UserMovieComment.comment_replies))
        .where(UserMovieComment.id == comment_id)
    )
    comment = await get_and_check_comment(stmt=comment_stmt, movie_id=movie_id, db=db)

    total_replies = comment.replies_count
    if not total_replies:
        raise no_comments_exception

    replies_stmt = (
        select(MovieCommentReply)
        .options(selectinload(MovieCommentReply.likes))
        .where(MovieCommentReply.movie_comment_id == comment_id)
    )
    replies_result = await db.execute(replies_stmt)
    replies = replies_result.scalars().all()
    reply_list = [CommentReplyListItemSchema.model_validate(reply) for reply in replies]
    return CommentReplyListResponseSchema(
        replies=reply_list, total_replies=total_replies
    )


@router.put(
    "/movies/{movie_id}/comments/{comment_id}/replies/{reply_id}/",
    response_model=CommentReplyUpdateResponseSchema,
    summary="Update a Comment Reply",
    description="Update your reply to a comment under a specific movie.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Reply does not belong to the comment.",
            "content": {
                "application/json": {
                    "example": {"detail": "This reply does not belong to this comment."}
                }
            },
        },
        403: {
            "description": "Forbidden - User is not the owner of the reply.",
            "content": {
                "application/json": {
                    "example": {"detail": "You are not the creator of this comment."}
                }
            },
        },
        404: {
            "description": "Not Found - Reply with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Comment not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during reply update.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when updating the reply."}
                }
            },
        },
    },
)
async def update_comment_reply(
    movie_id: int,
    comment_id: int,
    reply_id: int,
    reply_update: CommentReplyUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentReplyUpdateResponseSchema:
    """
    Comment reply update endpoint.

    Updates current user's reply to the given comment with the specified movie ID.
    Checks that the current user is the reply's creator and raises an HTTP 403 error if not.

    Args:
        movie_id (int): ID of the movie that was commented on.
        comment_id (int): ID of the comment to which the reply belongs.
        reply_id (int): ID of the reply to update.
        reply_update (CommentReplyUpdateSchema): Reply content to update.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CommentReplyUpdateResponseSchema: Reply details including its ID, content,
        the user ID and time of update.

    Raises:
        HTTPException:
            - 400 if the reply is not under the given comment.
            - 403 if the reply does not belong to the user.
            - 404 if the reply was not found.
            - 500 if an error occurred during reply update.
    """
    reply_stmt = select(MovieCommentReply).where(MovieCommentReply.id == reply_id)
    reply = await get_and_check_comment_reply(
        stmt=reply_stmt, comment_id=comment_id, user_id=current_user.id, db=db
    )

    try:
        reply.content = reply_update.content
        await db.flush()
        await db.commit()
        await db.refresh(reply)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when updating the reply.",
        )
    return CommentReplyUpdateResponseSchema.model_validate(reply)


@router.delete(
    "/movies/{movie_id}/comments/{comment_id}/replies/{reply_id}/",
    summary="Delete a Comment Reply",
    description="Delete your reply to a comment under a specific movie.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {
            "description": "Bad Request - Reply does not belong to the comment.",
            "content": {
                "application/json": {
                    "example": {"detail": "This reply does not belong to this comment."}
                }
            },
        },
        403: {
            "description": "Forbidden - User is not the owner of the reply.",
            "content": {
                "application/json": {
                    "example": {"detail": "You are not the creator of this comment."}
                }
            },
        },
        404: {
            "description": "Not Found - Reply with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Comment not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during reply deletion.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when deleting the reply."}
                }
            },
        },
    },
)
async def delete_comment_reply(
    movie_id: int,
    comment_id: int,
    reply_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Comment reply deletion endpoint.

    Deletes the current user's specified reply to the given comment.
    Checks that the current user is the reply's creator and raises an HTTP 403 error if not.

    Args:
        movie_id (int): ID of the movie that was commented on.
        comment_id (int): ID of the comment to which the reply belongs.
        reply_id (int): ID of the reply to update.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Raises:
        HTTPException:
            - 400 if the reply is not under the given comment.
            - 403 if the reply does not belong to the user.
            - 404 if the reply was not found.
            - 500 if an error occurred during reply update.
    """
    reply_stmt = select(MovieCommentReply).where(MovieCommentReply.id == reply_id)
    reply_to_delete = await get_and_check_comment_reply(
        stmt=reply_stmt, comment_id=comment_id, user_id=current_user.id, db=db
    )

    try:
        await db.delete(reply_to_delete)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when deleting the reply.",
        )


@router.post(
    "/movies/{movie_id}/comments/{comment_id}/replies/{reply_id}/like/",
    response_model=MessageResponseSchema,
    summary="Like a Comment Reply",
    description="Add or remove your like on a comment reply.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Reply does not belong to the comment.",
            "content": {
                "application/json": {
                    "example": {"detail": "This reply does not belong to this comment."}
                }
            },
        },
        404: {
            "description": "Not Found - Reply with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Comment not found."}}
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred when liking the reply.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred when liking the reply."}
                }
            },
        },
    },
)
async def like_comment_reply(
    movie_id: int,
    comment_id: int,
    reply_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Comment reply like endpoint.

    Allows the user to like the specified reply to a comment.
    If the reply is already liked by them, removes the like.

    Args:
        movie_id (int): ID of the movie that was commented on.
        comment_id (int): ID of the comment to which the reply belongs.
        reply_id (int): ID of the reply to like.
        background_tasks (BackgroundTasks): Background tasks to send email notifying
        the reply's owner of a new like.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Raises:
        HTTPException:
            - 400 if the reply is not under the given comment.
            - 404 if the reply was not found.
            - 500 if an error occurred when liking the reply.
    """
    reply_stmt = (
        select(MovieCommentReply)
        .options(
            joinedload(MovieCommentReply.user), selectinload(MovieCommentReply.likes)
        )
        .where(MovieCommentReply.id == reply_id)
    )
    reply = await get_and_check_comment_reply(
        stmt=reply_stmt, comment_id=comment_id, db=db
    )

    try:
        if current_user in reply.likes:
            reply.likes.remove(current_user)
            await db.commit()
            return MessageResponseSchema(message="Your like removed successfully.")

        reply_link = (
            f"{base_email_url}/movies/{movie_id}/comments/{comment_id}/replies/"
        )
        background_tasks.add_task(
            email_sender.send_comment_received_like_email, reply.user.email, reply_link
        )

        reply.likes.append(current_user)
        await db.commit()
        return MessageResponseSchema(message="Reply liked successfully.")
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when liking the reply.",
        )


@router.get(
    "/genres/",
    response_model=GenreListResponseSchema,
    summary="Genre List",
    description="Get a list of all genres with their movie count.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not Found - No genres were found.",
            "content": {
                "application/json": {
                    "examples": {
                        "no_genre": {
                            "summary": "Genre Not Found",
                            "value": {"detail": "No genres found."},
                        },
                        "no_movies": {
                            "summary": "Movies Not Found",
                            "value": {"detail": "No movies found."},
                        },
                    }
                }
            },
        }
    },
)
async def get_genres(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GenreListResponseSchema:
    """
    Genre list endpoint.

    Gets a list of all available genres with their movie count.

    Args:
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        GenreListResponseSchema: Genre list with movie counts.

    Raises:
        HTTPException:
            - 404 if no genres were found.
    """
    result = await db.execute(select(Genre).options(selectinload(Genre.movies)))
    genres = result.scalars().all()
    if not genres:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No genres found."
        )
    genres_list = [GenreListItemSchema.model_validate(genre) for genre in genres]
    return GenreListResponseSchema(genres=genres_list)


@router.get(
    "/genres/{genre_id}/",
    response_model=MovieListResponseSchema,
    summary="Movie List by Genre",
    description="Get a list of all movies with the given genre.",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Not Found - Genre with the given id not found.",
            "content": {
                "application/json": {"example": {"detail": "Genre not found."}}
            },
        }
    },
)
async def get_movies_by_genre(
    genre_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    """
    Detail genre endpoint with its movie list.

    Gets a list of movies belonging to the specified genre.

    Args:
        genre_id (int): The ID of the genre.
        page (int, optional): Page number of the page.
        per_page (int, optional): Number of items per page.
        current_user (User): Current user of the request.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MovieListResponseSchema: List of movies with this genre.

    Raises:
        HTTPException:
            - 404 if the given genre or movies were not found.
    """
    genre_stmt = (
        select(Genre).options(selectinload(Genre.movies)).where(Genre.id == genre_id)
    )
    genre_result = await db.execute(genre_stmt)
    genre = genre_result.scalar_one_or_none()
    if not genre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Genre not found."
        )

    filter_query = FilterParams(page=page, per_page=per_page, genres=genre.name)
    movies = await get_paginated_movies(
        filter_query=filter_query,
        base_url=f"/genres/{genre_id}/",
        db=db,
    )
    return MovieListResponseSchema(**movies)

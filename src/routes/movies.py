from typing import Annotated, Optional

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func, Select, desc, and_
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
    UserMovieFavoritesModel,
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
)
from security.account_utils import get_current_user

router = APIRouter()

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
    comment_stmt = select(UserMovieComment).limit(per_page).offset(offset)
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
    comment_result = await db.execute(comment_stmt)
    comment_to_update = comment_result.scalar_one_or_none()
    if not comment_to_update:
        raise comment_not_found_exception

    if comment_to_update.movie_id != movie_id:
        raise comment_under_wrong_movie_exception
    if comment_to_update.user_id != current_user.id:
        raise comment_not_own_exception

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
        comment_id (int): ID of the comment to update.
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
    comment_result = await db.execute(comment_stmt)
    comment_to_delete = comment_result.scalar_one_or_none()
    if not comment_to_delete:
        raise comment_not_found_exception

    if comment_to_delete.movie_id != movie_id:
        raise comment_under_wrong_movie_exception
    if comment_to_delete.user_id != current_user.id:
        raise comment_not_own_exception

    try:
        await db.delete(comment_to_delete)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred when deleting the comment.",
        )

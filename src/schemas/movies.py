from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from database.models.accounts import ReactionEnum
from schemas.examples.movies import (
    movie_list_item_schema_example,
    movie_list_response_schema_example,
    movie_detail_response_schema_example,
)


class BaseNameSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str


class GenreSchema(BaseNameSchema):
    pass


class GenreDetailSchema(BaseNameSchema):
    id: int


class GenreListItemSchema(GenreSchema):
    movie_count: int


class GenreListResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    genres: List[GenreListItemSchema]


class StarSchema(BaseNameSchema):
    pass


class StarDetailSchema(BaseNameSchema):
    id: int


class StarListResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stars: List[StarDetailSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int


class DirectorSchema(BaseNameSchema):
    pass


class CertificationSchema(BaseNameSchema):
    pass


class MovieSchema(BaseNameSchema):
    pass


class MovieCartItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    price: Optional[Decimal] = None
    genres: List[GenreSchema]
    year: int


class MovieListItemSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": [movie_list_item_schema_example]},
    )

    id: int
    name: str
    year: int
    imdb: float


class MovieListResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": [movie_list_response_schema_example]},
    )

    movies: List[MovieListItemSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int


class FavoriteMovieListResponseSchema(MovieListResponseSchema):
    pass


class PurchasedMovieListResponseSchema(MovieListResponseSchema):
    pass


class FilterParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(10, ge=1, le=100)
    order_by: Literal["id", "name", "year", "imdb"] = "id"

    name: Optional[str] = Field(
        None, min_length=1, max_length=250, description="Search by movie name."
    )
    description: Optional[str] = Field(
        None, min_length=1, description="Search movies by description."
    )
    certification: Optional[str] = Field(
        None, min_length=1, description="Search by certification."
    )

    year: Optional[int] = Field(None, description="Search by year.")
    year_to: Optional[int] = Field(None, description="Filter movies up to this year.")
    year_from: Optional[int] = Field(
        None, description="Filter movies starting from this year."
    )

    shorter_than: Optional[int] = Field(
        None, ge=1, description="Filter movies by duration shorter than this."
    )
    longer_than: Optional[int] = Field(
        None, ge=1, description="Filter movies by duration longer than this."
    )

    imdb_from: Optional[float] = Field(
        None, ge=0, description="Filter movies by imdb score."
    )
    imdb_to: Optional[float] = Field(
        None, ge=10, description="Filter movies by imdb score."
    )

    genres: Optional[str] = Field(
        None, min_length=1, description="Filter movies by genres."
    )
    directors: Optional[str] = Field(
        None, min_length=1, description="Filter movies by directors."
    )
    stars: Optional[str] = Field(
        None, min_length=1, description="Filter movies by actors."
    )


class BaseMovieDetailSchema(BaseModel):
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: str
    price: Optional[Decimal] = None
    certification: CertificationSchema
    genres: List[GenreSchema]
    directors: List[DirectorSchema]
    stars: List[StarSchema]


class MovieCreateRequestSchema(BaseMovieDetailSchema):
    pass


class MovieCreateResponseSchema(BaseMovieDetailSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: UUID


class MovieUpdateRequestSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=250)
    year: Optional[int] = None
    time: Optional[int] = None
    imdb: Optional[float] = None
    votes: Optional[int] = None
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: Optional[str] = Field(None, min_length=1)
    price: Optional[Decimal] = None
    certification: Optional[CertificationSchema] = None
    genres: Optional[List[GenreSchema]] = None
    directors: Optional[List[DirectorSchema]] = None
    stars: Optional[List[StarSchema]] = None


class MovieDetailSchema(BaseMovieDetailSchema):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": [movie_detail_response_schema_example]},
    )
    id: int
    uuid: UUID

    likes_count: int
    dislikes_count: int
    comments_count: int


class MovieReactionRequestSchema(BaseModel):
    reaction: ReactionEnum


class MovieRatingRequestSchema(BaseModel):
    rating: int = Field(ge=1, le=10)


class BaseCommentSchema(BaseModel):
    comment: str = Field(min_length=1, max_length=250)


class CommentCreateSchema(BaseCommentSchema):
    pass


class CommentUpdateSchema(BaseCommentSchema):
    pass


class BaseCommentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    comment: str
    user_id: int


class CommentCreateResponseSchema(BaseCommentResponseSchema):
    created_at: datetime


class CommentUpdateResponseSchema(BaseCommentResponseSchema):
    updated_at: datetime


class CommentListItemSchema(BaseCommentResponseSchema):
    created_at: datetime
    updated_at: datetime
    likes_count: int


class CommentListResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    comments: List[CommentListItemSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int


class BaseCommentReplySchema(BaseModel):
    content: str = Field(min_length=1, max_length=250)


class CommentReplyCreateSchema(BaseCommentReplySchema):
    pass


class CommentReplyUpdateSchema(BaseCommentReplySchema):
    pass


class BaseCommentReplyResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    user_id: int


class CommentReplyCreateResponseSchema(BaseCommentReplyResponseSchema):
    created_at: datetime


class CommentReplyUpdateResponseSchema(BaseCommentReplyResponseSchema):
    updated_at: datetime


class CommentReplyListItemSchema(BaseCommentReplyResponseSchema):
    created_at: datetime
    updated_at: datetime
    likes_count: int


class CommentReplyListResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_replies: int
    replies: List[CommentReplyListItemSchema]

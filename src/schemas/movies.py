from decimal import Decimal
from typing import List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class StarSchema(BaseNameSchema):
    pass


class DirectorSchema(BaseNameSchema):
    pass


class CertificationSchema(BaseNameSchema):
    pass


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


class MovieDetailSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": [movie_detail_response_schema_example]},
    )

    id: int
    uuid: UUID
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    meta_score: Optional[float]
    gross: Optional[float]
    description: str
    price: Optional[Decimal]
    certification: CertificationSchema
    genres: List[GenreSchema]
    directors: List[DirectorSchema]
    stars: List[StarSchema]

    likes_count: int
    dislikes_count: int

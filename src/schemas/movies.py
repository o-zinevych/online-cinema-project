from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.examples.movies import (
    movie_list_item_schema_example,
    movie_list_response_schema_example,
)


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

    name: Optional[str] = Field(
        None, min_length=1, max_length=250, description="Search by movie name."
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

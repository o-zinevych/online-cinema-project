from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from schemas.examples.movies import (
    movie_list_item_schema_example,
    movie_list_response_schema_example,
)


class MovieListItemSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": movie_list_item_schema_example},
    )

    id: int
    name: str
    year: int
    imdb_score: float


class MovieListResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": movie_list_response_schema_example},
    )

    movies: List[MovieListItemSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int

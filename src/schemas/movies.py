from pydantic import BaseModel, ConfigDict

from schemas.examples.movies import movie_list_item_schema_example


class MovieListItemSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"examples": movie_list_item_schema_example},
    )

    id: int
    name: str
    year: int
    imdb_score: float

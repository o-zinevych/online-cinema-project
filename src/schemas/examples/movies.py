certification_schema_example = {"name": "PG"}

genre_schema_example = {"name": "Comedy"}

director_schema_example = {"name": "Chris Columbus"}

star_schema_example = {"name": "Macaulay Culkin"}

movie_list_item_schema_example = {
    "id": 539,
    "name": "Home Alone",
    "year": 1990,
    "imdb": 7.7,
}

movie_list_response_schema_example = {
    "movies": [movie_list_item_schema_example],
    "prev_page": "/cinema/movies/?page=1&per_page=10",
    "next_page": "/cinema/movies/?page=2&per_page=10",
    "total_pages": 49,
    "total_items": 490,
}

movie_detail_response_schema_example = {
    "id": 539,
    "uuid": "7b4c11bf-1494-4326-9460-03a8378d5d35",
    "name": "Home Alone",
    "year": 1990,
    "time": 103,
    "imdb": 7.7,
    "votes": 706_000,
    "meta_score": 63,
    "gross": 476_684_675,
    "description": "An eight-year-old troublemaker, mistakenly left home alone, must defend his home against a pair of burglars on Christmas Eve.",
    "price": 3.99,
    "certification": certification_schema_example,
    "genres": [genre_schema_example],
    "directors": [director_schema_example],
    "stars": [star_schema_example],
}

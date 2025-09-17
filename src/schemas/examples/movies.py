movie_list_item_schema_example = {
    "id": 539,
    "name": "Home Alone",
    "year": 1990,
    "imdb_score": 7.7,
}

movie_list_response_schema_example = {
    "movies": [movie_list_item_schema_example],
    "prev_page": "/cinema/movies/?page=1&per_page=10",
    "next_page": "/cinema/movies/?page=2&per_page=10",
    "total_pages": 49,
    "total_items": 490,
}

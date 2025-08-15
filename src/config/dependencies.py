from pydantic_settings import BaseSettings

from config.settings import Settings


def get_settings() -> BaseSettings:
    """
    Returns:
        BaseSettings: An instance of the BaseSettings class.
    """
    return Settings()

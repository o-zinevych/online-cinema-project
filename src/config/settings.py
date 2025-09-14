import os
from pathlib import Path

from pydantic_settings import BaseSettings


class BaseAppSettings(BaseSettings):
    BASE_DIR: Path = Path(__file__).parent.parent
    PATH_TO_DB: str = str(BASE_DIR / "database" / "cinema.db")

    EMAIL_HOST: str = os.getenv("EMAIL_HOST", "host")
    EMAIL_PORT: int = os.getenv("EMAIL_PORT", 25)
    EMAIL_HOST_USER: str = os.getenv("EMAIL_HOST_USER", "test_user")
    EMAIL_HOST_PASSWORD: str = os.getenv("EMAIL_HOST_PASSWORD", "test_password")
    EMAIL_USE_TLS: bool = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"

    EMAIL_TEMPLATES_PATH: str = str(BASE_DIR / "notifications" / "templates")
    ACTIVATION_EMAIL_TEMPLATE_NAME: str = "activation_request.html"
    ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME: str = "activation_complete.html"
    PASSWORD_RESET_EMAIL_TEMPLATE_NAME: str = "password_reset_request.html"
    OLD_PASSWORD_RESET_EMAIL_TEMPLATE_NAME: str = "old_password_reset_request.html"
    PASSWORD_RESET_COMPLETE_EMAIL_TEMPLATE_NAME: str = "password_reset_complete.html"

    LOGIN_TIME_DAYS: int = 7

    SECRET_KEY_ACCESS: str = os.getenv("SECRET_KEY_ACCESS", str(os.urandom(32)))
    SECRET_KEY_REFRESH: str = os.getenv("SECRET_KEY_REFRESH", str(os.urandom(32)))
    JWT_SIGNING_ALGORITHM: str = os.getenv("JWT_SIGNING_ALGORITHM", "HS256")

    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
    )

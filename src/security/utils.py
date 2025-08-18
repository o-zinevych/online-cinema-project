import secrets

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=14, deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

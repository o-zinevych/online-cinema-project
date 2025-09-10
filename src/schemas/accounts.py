from pydantic import BaseModel, EmailStr, field_validator, ConfigDict

from database.validators.accounts import validate_password_strength


class BasePasswordSchema(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        return validate_password_strength(value)


class BaseEmailPasswordSchema(BasePasswordSchema):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        return value.lower()


class UserRegistrationRequestSchema(BaseEmailPasswordSchema):
    pass


class UserRegistrationResponseSchema(BaseModel):
    id: int
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class UserActivationRequestSchema(BaseModel):
    email: EmailStr


class PasswordResetRequestSchema(BaseModel):
    email: EmailStr
    password_forgotten: bool


class PasswordResetCompleteRequestSchema(BasePasswordSchema):
    token: str


class MessageResponseSchema(BaseModel):
    message: str

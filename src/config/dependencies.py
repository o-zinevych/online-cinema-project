from fastapi import Depends
from pydantic_settings import BaseSettings

from config.settings import BaseAppSettings
from notifications.emails import EmailSender
from notifications.interfaces import EmailSenderInterface
from security.interfaces import JWTAuthManagerInterface
from security.token_manager import JWTAuthManager


def get_settings() -> BaseSettings:
    """
    Returns:
        BaseSettings: An instance of the BaseSettings class.
    """
    return BaseAppSettings()


def get_account_email_sender(
    settings: BaseSettings = Depends(get_settings),
) -> EmailSenderInterface:
    """
    Returns an instance of the EmailSenderInterface class.

    Creates an EmailSender using the given settings, which include the email host,
    port, credentials, TLS usage and various email notification template directories.
    This allows the app to send different kinds of account email notifications.

    Args:
        settings (BaseAppSettings, optional): The application settings.

    Returns:
        EmailSenderInterface: An instance of the EmailSender with the appropriate configuration.
    """
    return EmailSender(
        hostname=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        email=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        template_dir=settings.EMAIL_TEMPLATES_PATH,
        activation_email_template_name=settings.ACTIVATION_EMAIL_TEMPLATE_NAME,
        activation_complete_email_template_name=settings.ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME,
        password_reset_email_template_name=settings.PASSWORD_RESET_EMAIL_TEMPLATE_NAME,
        old_password_reset_email_template_name=settings.OLD_PASSWORD_RESET_EMAIL_TEMPLATE_NAME,
        password_reset_complete_email_template_name=settings.PASSWORD_RESET_COMPLETE_EMAIL_TEMPLATE_NAME,
        comment_received_reply_email_template_name=settings.COMMENT_RECEIVED_REPLY_EMAIL_TEMPLATE_NAME,
    )


def get_jwt_auth_manager(
    settings: BaseAppSettings = Depends(get_settings),
) -> JWTAuthManagerInterface:
    """
    Create and return a JWT authentication manager instance.

    This function uses the given settings to instantiate the JWTAuthManager class based
    on the JWTAuthManagerInterface. The manager is configured using the specified signing
    algorithm and secret keys for access and refresh tokens.

    Args:
        settings (BaseAppSettings, optional): The application settings.

    Returns:
        JWTAuthManagerInterface: An instance of the JWTAuthManager configured with the
        appropriate secret keys and algorithm.
    """
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM,
    )

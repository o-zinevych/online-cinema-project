from fastapi import Depends
from pydantic_settings import BaseSettings

from config.settings import BaseAppSettings
from notifications.emails import EmailSender
from notifications.interfaces import EmailSenderInterface


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
    )

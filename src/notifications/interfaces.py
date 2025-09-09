from abc import ABC, abstractmethod


class EmailSenderInterface(ABC):
    @abstractmethod
    async def send_activation_email(self, email: str, activation_link: str) -> None:
        """
        Send an account activation email asynchronously.

        Args:
            email (str): The recipient's email address.
            activation_link (str): The activation link to include in the email.
        """
        pass

    @abstractmethod
    async def send_activation_complete_email(self, email: str, login_link: str) -> None:
        """
        Send an account activation complete email asynchronously.

        Args:
            email (str): The recipient's email address.
            login_link (str): The login link to include in the email.
        """

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from jinja2 import Environment, FileSystemLoader

from exceptions.email import BaseEmailError
from notifications.interfaces import EmailSenderInterface


class EmailSender(EmailSenderInterface):
    def __init__(
        self,
        hostname: str,
        port: int,
        email: str,
        password: str,
        use_tls: bool,
        template_dir: str,
        activation_email_template_name: str,
        activation_complete_email_template_name: str,
    ) -> None:
        self._hostname = hostname
        self._port = port
        self._email = email
        self._password = password
        self._use_tls = use_tls
        self._activation_email_template_name = activation_email_template_name
        self._activation_complete_email_template_name = (
            activation_complete_email_template_name
        )
        self._env = Environment(loader=FileSystemLoader(template_dir))

    async def _send_email(
        self, recipient: str, subject: str, html_content: str
    ) -> None:
        """
        Send an email with the given subject and HTML content asynchronously.

        Args:
            recipient (str): The recipient's email address.
            subject (str): The subject of the email.
            html_content (str): The HTML content of the email.

        Raises:
            BaseEmailError: If sending the email fails.
        """
        message = MIMEMultipart()
        message["From"] = self._email
        message["To"] = recipient
        message["Subject"] = subject
        message.attach(MIMEText(html_content, "html"))

        try:
            smtp_client = aiosmtplib.SMTP(
                hostname=self._hostname, port=self._port, start_tls=self._use_tls
            )
            await smtp_client.connect()
            if self._use_tls:
                await smtp_client.starttls()
            await smtp_client.login(self._email, self._password)
            await smtp_client.sendmail(self._email, [recipient], message.as_string())
            await smtp_client.quit()
        except aiosmtplib.SMTPException as error:
            logging.error(f"Failed to send email to {recipient}: {error}")
            raise BaseEmailError(f"Failed to send email to {recipient}: {error}")

    async def send_activation_email(self, email: str, activation_link: str) -> None:
        """
        Send an account activation email asynchronously.

        Args:
            email (str): The recipient's email address.
            activation_link (str): The activation link to include in the email.
        """
        template = self._env.get_template(self._activation_email_template_name)
        html = template.render(email=email, activation_link=activation_link)
        subject = "Account Activation"
        await self._send_email(email, subject, html)

    async def send_activation_complete_email(self, email: str, login_link: str) -> None:
        """
        Send an account activation complete email asynchronously.

        Args:
            email (str): The recipient's email address.
            login_link (str): The login link to include in the email.
        """
        template = self._env.get_template(self._activation_complete_email_template_name)
        html = template.render(login_link=login_link)
        subject = "Account Activated"
        await self._send_email(email, subject, html)

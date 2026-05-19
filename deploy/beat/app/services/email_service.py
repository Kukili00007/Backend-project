from __future__ import annotations

import base64
from email.message import EmailMessage

import httpx

from app.config import Settings


class GmailOAuth2EmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> None:
        if not self.settings.email_enabled:
            raise RuntimeError("Email delivery is disabled. Set EMAIL_ENABLED=true in DeployRocks env.")
        self._validate_configuration()
        access_token = await self._fetch_access_token()
        raw_message = self._build_raw_message(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw_message},
            )
            response.raise_for_status()

    def _validate_configuration(self) -> None:
        missing = [
            name
            for name, value in {
                "GOOGLE_OAUTH_CLIENT_ID": self.settings.google_oauth_client_id,
                "GOOGLE_OAUTH_CLIENT_SECRET": self.settings.google_oauth_client_secret,
                "GOOGLE_OAUTH_REFRESH_TOKEN": self.settings.google_oauth_refresh_token,
                "GMAIL_SENDER_EMAIL": self.settings.effective_sender_email,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing email configuration: {', '.join(missing)}")

    async def _fetch_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                self.settings.google_oauth_token_uri,
                data={
                    "client_id": self.settings.google_oauth_client_id,
                    "client_secret": self.settings.google_oauth_client_secret,
                    "refresh_token": self.settings.google_oauth_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            payload = response.json()

        access_token = payload.get("access_token")
        if not access_token:
            raise RuntimeError("Google OAuth2 token response did not include access_token.")
        return str(access_token)

    def _build_raw_message(
        self,
        *,
        recipient_email: str,
        subject: str,
        body_text: str,
        body_html: str | None,
    ) -> str:
        message = EmailMessage()
        message["To"] = recipient_email
        message["From"] = self.settings.effective_sender_email
        message["Subject"] = subject
        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")
        return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

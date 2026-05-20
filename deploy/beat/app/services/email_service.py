from __future__ import annotations

import httpx

from app.config import Settings


class SendGridEmailService:
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
            raise RuntimeError("Email delivery is disabled. Set EMAIL_ENABLED=true.")
        if not self.settings.sendgrid_api_key:
            raise RuntimeError("Missing SENDGRID_API_KEY env var.")

        content = [{"type": "text/plain", "value": body_text}]
        if body_html:
            content.append({"type": "text/html", "value": body_html})

        payload = {
            "personalizations": [{"to": [{"email": recipient_email}]}],
            "from": {"email": self.settings.effective_sender_email},
            "subject": subject,
            "content": content,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {self.settings.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code not in (200, 202):
                raise RuntimeError(
                    f"SendGrid error {response.status_code}: {response.text[:500]}"
                )


# Keep for backwards compatibility
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
        import base64
        from email.message import EmailMessage

        if not self.settings.email_enabled:
            raise RuntimeError("Email delivery is disabled. Set EMAIL_ENABLED=true.")
        missing = [
            name
            for name, value in {
                "GOOGLE_OAUTH_CLIENT_ID": self.settings.google_oauth_client_id,
                "GOOGLE_OAUTH_CLIENT_SECRET": self.settings.google_oauth_client_secret,
                "GOOGLE_OAUTH_REFRESH_TOKEN": self.settings.google_oauth_refresh_token,
                "GMAIL_SENDER_EMAIL": self.settings.gmail_sender_email,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing email configuration: {', '.join(missing)}")

        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.post(
                self.settings.google_oauth_token_uri,
                data={
                    "client_id": self.settings.google_oauth_client_id,
                    "client_secret": self.settings.google_oauth_client_secret,
                    "refresh_token": self.settings.google_oauth_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise RuntimeError("Google OAuth2 did not return access_token.")

        message = EmailMessage()
        message["To"] = recipient_email
        message["From"] = self.settings.effective_sender_email
        message["Subject"] = subject
        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
            response.raise_for_status()


def get_email_service(settings: Settings) -> SendGridEmailService | GmailOAuth2EmailService:
    if settings.email_provider == "sendgrid":
        return SendGridEmailService(settings)
    return GmailOAuth2EmailService(settings)

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("api.public.contact")

router = APIRouter(tags=["public"])


class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str


@router.post("/contact")
async def contact_form(
    name: Annotated[str, Form()],
    email: Annotated[EmailStr, Form()],
    subject: Annotated[str, Form()],
    message: Annotated[str, Form()],
):
    """Description:
    Handles contact form submissions and sends an email to the configured destination.
    """
    logger.info("Received contact form submission from: %s", email)

    # Construct email
    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_USER
    msg["To"] = settings.CONTACT_EMAIL_DESTINATION
    msg["Subject"] = f"REHA Apps Contact: {subject}"

    body = f"Name: {name}\nEmail: {email}\nSubject: {subject}\n\nMessage:\n{message}"
    msg.attach(MIMEText(body, "plain"))

    try:
        # Send email in a threadpool to avoid blocking the async loop
        import asyncio

        loop = asyncio.get_running_loop()

        def send_email():
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(
                    settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value()
                )
                server.send_message(msg)

        await loop.run_in_executor(None, send_email)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Your message has been sent successfully!",
            },
        )
    except Exception as e:
        logger.error("Failed to send contact email: %s", e)
        # Return 200 to user but log error (or 500 if we want them to know)
        # We'll return 500 so they can try again or see something went wrong.
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to send message. Please try again later or email us directly."
            ),
        )

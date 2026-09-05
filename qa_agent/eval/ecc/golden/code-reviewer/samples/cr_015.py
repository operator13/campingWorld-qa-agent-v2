"""Notification service with proper structured logging."""
import json
import logging
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email notification via API with structured logging."""
    logger.info("Sending email", extra={"recipient": to, "subject": subject})
    payload = json.dumps({"to": to, "subject": subject, "body": body}).encode()
    req = urllib.request.Request(
        "https://api.example.com/email",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(req)
        logger.info(
            "Email sent successfully",
            extra={"recipient": to, "status": response.status},
        )
        return True
    except urllib.error.URLError as e:
        logger.error(
            "Email delivery failed",
            extra={"recipient": to, "error": str(e)},
            exc_info=True,
        )
        return False


def send_sms(phone: str, message: str, max_length: int = 160) -> bool:
    """Send an SMS notification with proper logging."""
    if len(message) > max_length:
        logger.warning(
            "SMS message truncated",
            extra={"phone": phone, "original_length": len(message)},
        )
        message = message[:max_length]

    logger.info("Sending SMS", extra={"phone": phone, "length": len(message)})
    try:
        payload = json.dumps({"phone": phone, "message": message}).encode()
        req = urllib.request.Request(
            "https://api.example.com/sms",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req)
        logger.info("SMS sent", extra={"phone": phone})
        return True
    except urllib.error.URLError as e:
        logger.error("SMS failed", extra={"phone": phone, "error": str(e)})
        return False

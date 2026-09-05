"""Notification service using print() instead of logging."""
import json
import urllib.request


def send_email_notification(to: str, subject: str, body: str) -> bool:
    """Send an email notification via API."""
    print(f"Sending email to {to}")
    payload = json.dumps({"to": to, "subject": subject, "body": body}).encode()
    req = urllib.request.Request(
        "https://api.example.com/email",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(req)
        print(f"Email sent successfully, status: {response.status}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_sms_notification(phone: str, message: str) -> bool:
    """Send an SMS notification."""
    print(f"Sending SMS to {phone}")
    if len(message) > 160:
        print("WARNING: SMS message exceeds 160 characters, truncating")
        message = message[:160]
    try:
        payload = json.dumps({"phone": phone, "message": message}).encode()
        req = urllib.request.Request(
            "https://api.example.com/sms",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req)
        print(f"SMS sent to {phone}")
        return True
    except Exception as e:
        print(f"SMS failed for {phone}: {e}")
        return False

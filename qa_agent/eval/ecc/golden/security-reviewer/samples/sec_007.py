"""Service with base64-encoded secret hidden in code."""
import base64
import httpx
from fastapi import FastAPI

app = FastAPI()

# Configuration constants
SERVICE_NAME = "payment-gateway"
_AUTH_TOKEN = base64.b64decode(
    "c2stbGl2ZS1hYmMxMjNkZWY0NTZnaGk3ODlqa2wwMTJtbm8="
).decode()


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {_AUTH_TOKEN}",
        "Content-Type": "application/json",
        "X-Service": SERVICE_NAME,
    }


@app.post("/api/payments/process")
async def process_payment(amount: int, currency: str = "usd"):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.paymentprovider.com/v1/charges",
            headers=get_headers(),
            json={"amount": amount, "currency": currency},
        )
    return resp.json()


@app.get("/api/payments/{payment_id}")
async def get_payment(payment_id: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.paymentprovider.com/v1/charges/{payment_id}",
            headers=get_headers(),
        )
    return resp.json()

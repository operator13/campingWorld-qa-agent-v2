"""Service with proper secret management via environment variables."""
import os
import httpx
from fastapi import FastAPI, HTTPException

app = FastAPI()


def get_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY environment variable is required")
    return key


def get_stripe_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY environment variable is required")
    return key


@app.get("/api/generate")
async def generate_text(prompt: str):
    api_key = get_api_key()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "gpt-4", "messages": [{"role": "user", "content": prompt}]},
        )
    return response.json()


@app.post("/api/charge")
async def charge_customer(amount: int, token: str):
    stripe_key = get_stripe_key()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.stripe.com/v1/charges",
            headers={"Authorization": f"Bearer {stripe_key}"},
            data={"amount": amount, "currency": "usd", "source": token},
        )
    return response.json()

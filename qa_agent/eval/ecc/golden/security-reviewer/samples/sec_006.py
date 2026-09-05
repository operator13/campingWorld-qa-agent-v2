"""Service with hardcoded API key."""
import httpx
from fastapi import FastAPI

app = FastAPI()

# NOTE: These are intentionally fake keys for eval testing (planted vulnerability)
OPENAI_API_KEY = "FAKE-KEY-FOR-EVAL-do-not-use-abc123def456"
STRIPE_SECRET = "FAKE-KEY-FOR-EVAL-do-not-use-xyz789ghi012"


@app.get("/api/generate")
async def generate_text(prompt: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    return response.json()


@app.post("/api/charge")
async def charge_customer(amount: int, token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.stripe.com/v1/charges",
            headers={"Authorization": f"Bearer {STRIPE_SECRET}"},
            data={"amount": amount, "currency": "usd", "source": token},
        )
    return response.json()

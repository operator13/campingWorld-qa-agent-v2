"""Properly structured async endpoint with httpx and response model."""
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class WeatherResponse(BaseModel):
    location: str
    temperature_f: float
    conditions: str


@router.get("/weather/{zip_code}", response_model=WeatherResponse)
async def get_weather(zip_code: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.weather.example.com/v1/forecast?zip={zip_code}",
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()

    return WeatherResponse(
        location=data["location"],
        temperature_f=data["temp"],
        conditions=data["conditions"],
    )

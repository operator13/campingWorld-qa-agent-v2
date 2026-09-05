"""Pydantic schema with mutable default argument."""
from pydantic import BaseModel
from fastapi import APIRouter

router = APIRouter()


class CreateCampaignRequest(BaseModel):
    name: str
    tags: list = []
    metadata: dict = {}
    recipients: list[str] = []


class CampaignResponse(BaseModel):
    id: int
    name: str
    tags: list
    recipient_count: int


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(payload: CreateCampaignRequest):
    return CampaignResponse(
        id=1,
        name=payload.name,
        tags=payload.tags,
        recipient_count=len(payload.recipients),
    )

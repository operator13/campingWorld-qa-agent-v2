"""Correct Pydantic v2 schema with Field and proper defaults."""
from pydantic import BaseModel, Field
from fastapi import APIRouter

router = APIRouter()


class NotificationPreferences(BaseModel):
    email_enabled: bool = True
    sms_enabled: bool = False
    channels: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class UserProfile(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    display_name: str
    preferences: NotificationPreferences = Field(
        default_factory=NotificationPreferences
    )


class UserProfileResponse(BaseModel):
    id: int
    username: str
    display_name: str
    preferences: NotificationPreferences


@router.post("/users/profile", response_model=UserProfileResponse)
async def create_profile(profile: UserProfile):
    return UserProfileResponse(
        id=42,
        username=profile.username,
        display_name=profile.display_name,
        preferences=profile.preferences,
    )

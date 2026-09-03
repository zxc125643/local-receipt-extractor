from __future__ import annotations

from pydantic import BaseModel


class OAuth2Settings(BaseModel):
    """
    OAuth2设置
    """
    client_id: str
    redirect_url: str
    scopes: list[str]


class SmsSettings(BaseModel):
    provider: str = ""
    api_key: str = ""
    country: str = "Indonesia"
    operator: str = "any"


class AppSettingsResponse(BaseModel):
    oauth2: OAuth2Settings
    sms: SmsSettings = SmsSettings()

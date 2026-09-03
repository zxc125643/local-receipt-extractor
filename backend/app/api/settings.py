import json
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import assert_desktop_auth, get_db_session
from backend.app.db.models import AppSettings
from backend.app.schemas.settings import AppSettingsResponse, OAuth2Settings, SmsSettings

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(assert_desktop_auth)])


def _get_or_create_app_settings(session: Session) -> AppSettings:
    """
    获取或创建应用设置
    """
    settings = session.scalar(select(AppSettings))
    if not settings:
        settings = AppSettings(
            oauth2_client_id="",
            oauth2_redirect_url="",
            oauth2_scopes="[]"
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


@router.get("/oauth2", response_model=OAuth2Settings)
def get_oauth2_settings(session: Session = Depends(get_db_session)) -> OAuth2Settings:
    """
    获取OAuth2设置
    """
    settings = _get_or_create_app_settings(session)
    scopes = json.loads(settings.oauth2_scopes) if settings.oauth2_scopes else []
    return OAuth2Settings(
        client_id=settings.oauth2_client_id,
        redirect_url=settings.oauth2_redirect_url,
        scopes=json.loads(settings.oauth2_scopes)
    )


@router.get("/sms", response_model=SmsSettings)
def get_sms_settings(session: Session = Depends(get_db_session)) -> SmsSettings:
    settings = _get_or_create_app_settings(session)
    return SmsSettings(
        provider=settings.sms_provider or "",
        api_key=settings.sms_api_key or "",
        country=settings.sms_country or "Indonesia",
        operator=settings.sms_operator or "any",
    )


@router.put("/sms", response_model=SmsSettings)
def update_sms_settings(
    payload: SmsSettings,
    session: Session = Depends(get_db_session)
) -> SmsSettings:
    settings = _get_or_create_app_settings(session)
    settings.sms_provider = payload.provider
    settings.sms_api_key = payload.api_key
    settings.sms_country = payload.country
    settings.sms_operator = payload.operator
    settings.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(settings)
    return payload


@router.put("/oauth2", response_model=OAuth2Settings)
def update_oauth2_settings(
    payload: OAuth2Settings,
    session: Session = Depends(get_db_session)
) -> OAuth2Settings:
    """
    更新OAuth2设置
    """
    settings = _get_or_create_app_settings(session)
    settings.oauth2_client_id = payload.client_id
    settings.oauth2_redirect_url = payload.redirect_url
    settings.oauth2_scopes = json.dumps(payload.scopes)
    settings.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(settings)

    return OAuth2Settings(
        client_id=settings.oauth2_client_id,
        redirect_url=settings.oauth2_redirect_url,
        scopes=json.loads(settings.oauth2_scopes)
    )

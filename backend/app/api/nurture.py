from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import assert_desktop_auth, get_db_session
from backend.app.db.models import Account
from backend.app.services.nurture_service import NurtureService

router = APIRouter(prefix="/nurture", tags=["nurture"], dependencies=[Depends(assert_desktop_auth)])

nurture_service = NurtureService()


@router.post("/start/{account_id}")
def start_nurture(account_id: int, session: Session = Depends(get_db_session)):
    account = session.scalar(select(Account).where(Account.id == account_id))
    if not account:
        raise HTTPException(status_code=404, detail="account not found")

    account.nurture_status = "running"
    account.nurture_stage = 0
    session.commit()

    success, msg = nurture_service.run_nurture_cycle(account)
    return {"account_id": account_id, "success": success, "message": msg}


@router.post("/batch")
def start_batch_nurture(limit: int = 3, session: Session = Depends(get_db_session)):
    candidates = nurture_service.get_nurture_candidates(session, limit=limit)
    results = []
    for account in candidates:
        account.nurture_status = "running"
        session.commit()
        success, msg = nurture_service.run_nurture_cycle(account)
        results.append({
            "account_id": account.id,
            "email": account.email,
            "success": success,
            "message": msg,
        })
    return {"total": len(results), "results": results}


@router.get("/candidates")
def get_candidates(limit: int = 10, session: Session = Depends(get_db_session)):
    candidates = nurture_service.get_nurture_candidates(session, limit=limit)
    return [
        {
            "id": a.id,
            "email": a.email,
            "nurture_stage": a.nurture_stage,
            "nurture_count": a.nurture_count,
            "nurture_status": a.nurture_status,
            "nurture_next_at": str(a.nurture_next_at) if a.nurture_next_at else None,
        }
        for a in candidates
    ]


@router.get("/status/{account_id}")
def get_nurture_status(account_id: int, session: Session = Depends(get_db_session)):
    account = session.scalar(select(Account).where(Account.id == account_id))
    if not account:
        raise HTTPException(status_code=404)
    return {
        "id": account.id,
        "email": account.email,
        "nurture_stage": account.nurture_stage,
        "nurture_count": account.nurture_count,
        "nurture_status": account.nurture_status,
        "nurture_next_at": str(account.nurture_next_at) if account.nurture_next_at else None,
    }

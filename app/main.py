"""
Closira Backend - Core FastAPI Application

Handles incoming customer inquiries, async background job dispatching, 
and manual state management (escalations, follow-ups).
"""

import json
import logging
from datetime import datetime

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import Enquiry, EnquiryEvent, EnquiryStatus
from app.schemas import (
    EnquiryCreate,
    EnquiryCreatedResponse,
    EnquiryEventOut,
    EnquiryOut,
    EscalateRequest,
    FollowUpRequest,
    HealthResponse,
)
from app.tasks import _log_event, process_enquiry

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Closira Backend API",
    description="Inbound lead management system with automated SOP processing.",
    version="1.0.0",
)

logger = logging.getLogger(__name__)


@app.post(
    "/enquiry",
    response_model=EnquiryCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Accept incoming customer enquiry",
    tags=["Enquiries"],
)
def create_enquiry(
    payload: EnquiryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Submits a new customer inquiry. Returns a tracking job_id immediately 
    and offloads SOP processing to a background worker loop.
    """
    enquiry = Enquiry(
        customer_name=payload.customer_name,
        channel=payload.channel,
        message=payload.message,
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)

    _log_event(db, enquiry.id, "created", f"Enquiry received via {payload.channel}.")

    logger.info(
        json.dumps({
            "event": "enquiry_created",
            "enquiry_id": enquiry.id,
            "channel": payload.channel,
            "customer": payload.customer_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
    )

    background_tasks.add_task(process_enquiry, enquiry.id)

    return EnquiryCreatedResponse(job_id=enquiry.id)


@app.post(
    "/enquiry/{id}/follow-up",
    status_code=status.HTTP_200_OK,
    summary="Schedule future follow-up template",
    tags=["Enquiries"],
)
def schedule_follow_up(
    id: str,
    payload: FollowUpRequest,
    db: Session = Depends(get_db),
):
    """
    Schedules an outbound response template to push to the customer after a delay.
    Fails if the enquiry is currently escalated to a human.
    """
    enquiry = db.query(Enquiry).filter(Enquiry.id == id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found.")
        
    if enquiry.status == EnquiryStatus.ESCALATED:
        raise HTTPException(
            status_code=400,
            detail="Cannot schedule follow-ups on active human escalations.",
        )

    enquiry.follow_up_delay_minutes = str(payload.delay_minutes)
    enquiry.follow_up_message_template = payload.message_template
    enquiry.status = EnquiryStatus.FOLLOW_UP_SCHEDULED
    db.commit()

    _log_event(
        db, id, "follow_up_scheduled",
        f"Follow-up queued for +{payload.delay_minutes}m.",
    )

    logger.info(
        json.dumps({
            "event": "follow_up_scheduled",
            "enquiry_id": id,
            "delay_minutes": payload.delay_minutes,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
    )

    return {
        "message": f"Follow-up scheduled successfully.",
        "enquiry_id": id,
        "status": enquiry.status,
    }


@app.post(
    "/enquiry/{id}/escalate",
    status_code=status.HTTP_200_OK,
    summary="Manual human agent escalation",
    tags=["Enquiries"],
)
def escalate_enquiry(
    id: str,
    payload: EscalateRequest,
    db: Session = Depends(get_db),
):
    """
    Flags an inquiry for manual human intervention, overriding previous automation tracks.
    """
    enquiry = db.query(Enquiry).filter(Enquiry.id == id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found.")
        
    if enquiry.status == EnquiryStatus.ESCALATED:
        raise HTTPException(status_code=400, detail="Enquiry is already flagged for escalation.")

    enquiry.status = EnquiryStatus.ESCALATED
    enquiry.escalation_reason = payload.reason
    db.commit()

    _log_event(db, id, "escalated", f"Manual escalation triggered: {payload.reason}")

    logger.info(
        json.dumps({
            "event": "escalation_triggered",
            "enquiry_id": id,
            "reason": payload.reason,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
    )

    return {
        "message": "Enquiry successfully escalated to support pool.",
        "enquiry_id": id,
    }


@app.get(
    "/enquiry/{id}/history",
    response_model=EnquiryOut,
    status_code=status.HTTP_200_OK,
    summary="Fetch audit timeline and history",
    tags=["Enquiries"],
)
def get_history(id: str, db: Session = Depends(get_db)):
    """
    Returns the target inquiry object along with its structured lifecycle log events 
    sorted in chronological order.
    """
    enquiry = db.query(Enquiry).filter(Enquiry.id == id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found.")

    events = (
        db.query(EnquiryEvent)
        .filter(EnquiryEvent.enquiry_id == id)
        .order_by(EnquiryEvent.created_at.asc())
        .all()
    )

    result = EnquiryOut.model_validate(enquiry)
    result.events = [EnquiryEventOut.model_validate(e) for e in events]
    return result


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service dependency heartbeat",
    tags=["System"],
)
def health_check(db: Session = Depends(get_db)):
    """
    Verifies runtime API liveness and tests storage backend query execution loop.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    return HealthResponse(
        status="ok",
        database=db_status,
        app=settings.APP_NAME,
    )
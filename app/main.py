"""
Closira Backend  main FastAPI application.

Endpoints:
  POST   /enquiry                   create inbound enquiry (non-blocking)
  POST   /enquiry/{id}/follow-up    schedule a follow-up
  POST   /enquiry/{id}/escalate     escalate to human agent
  GET    /enquiry/{id}/history      full conversation history + status timeline
  GET    /health                    API + DB health check
"""

import json
import logging
from datetime import datetime

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
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

# ── Bootstrap ─────────────────────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Closira Backend API",
    description=(
        "Customer enquiry-handling backend for Closira. "
        "Handles inbound enquiries via WhatsApp, email, and phone. "
        "Processes them asynchronously with SOP matching."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

logger = logging.getLogger(__name__)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post(
    "/enquiry",
    response_model=EnquiryCreatedResponse,
    status_code=202,
    summary="Create new inbound customer enquiry",
    tags=["Enquiries"],
    responses={
        202: {"description": "Enquiry accepted. Processing begins in background."},
        422: {"description": "Validation error  check request body."},
    },
)
def create_enquiry(
    payload: EnquiryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Submit a new inbound customer enquiry.

    - Returns a **job_id** (UUID) immediately; does not block.
    - A background task runs SOP keyword matching and updates the record.
    - Supported channels: `whatsapp`, `email`, `call`.

    **Example request body:**
    ```json
    {
      "channel": "whatsapp",
      "customer_name": "Rahul Sharma",
      "message": "Hi, I'd like to book an appointment for next Monday."
    }
    ```
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

    logger.info(json.dumps({
        "event": "enquiry_created",
        "enquiry_id": enquiry.id,
        "channel": payload.channel,
        "customer": payload.customer_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }))

    background_tasks.add_task(process_enquiry, enquiry.id)

    return EnquiryCreatedResponse(job_id=enquiry.id)


@app.post(
    "/enquiry/{id}/follow-up",
    status_code=200,
    summary="Schedule a follow-up for an open enquiry",
    tags=["Enquiries"],
    responses={
        200: {"description": "Follow-up scheduled."},
        400: {"description": "Cannot schedule follow-up on an escalated enquiry."},
        404: {"description": "Enquiry not found."},
    },
)
def schedule_follow_up(
    id: str,
    payload: FollowUpRequest,
    db: Session = Depends(get_db),
):
    """
    Schedule a follow-up message for an open enquiry.

    - **delay_minutes**: How many minutes until the follow-up is sent (110080).
    - **message_template**: Optional template string; use `{customer_name}` as a placeholder.
    - Escalated enquiries cannot have follow-ups scheduled.

    **Example request body:**
    ```json
    {
      "delay_minutes": 30,
      "message_template": "Hi {customer_name}, just checking in on your enquiry!"
    }
    ```
    """
    enquiry: Enquiry | None = db.query(Enquiry).filter(Enquiry.id == id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found.")
    if enquiry.status == EnquiryStatus.ESCALATED:
        raise HTTPException(
            status_code=400,
            detail="Escalated enquiries cannot have follow-ups scheduled. Resolve escalation first.",
        )

    enquiry.follow_up_delay_minutes = str(payload.delay_minutes)
    enquiry.follow_up_message_template = payload.message_template
    enquiry.status = EnquiryStatus.FOLLOW_UP_SCHEDULED
    db.commit()

    _log_event(
        db, id, "follow_up_scheduled",
        f"Follow-up scheduled in {payload.delay_minutes} min. Template: {payload.message_template or 'default'}",
    )

    logger.info(json.dumps({
        "event": "follow_up_scheduled",
        "enquiry_id": id,
        "delay_minutes": payload.delay_minutes,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }))

    return {
        "message": f"Follow-up scheduled in {payload.delay_minutes} minutes.",
        "enquiry_id": id,
        "status": enquiry.status,
    }


@app.post(
    "/enquiry/{id}/escalate",
    status_code=200,
    summary="Escalate an enquiry to a human agent",
    tags=["Enquiries"],
    responses={
        200: {"description": "Enquiry escalated."},
        400: {"description": "Enquiry is already escalated."},
        404: {"description": "Enquiry not found."},
    },
)
def escalate_enquiry(
    id: str,
    payload: EscalateRequest,
    db: Session = Depends(get_db),
):
    """
    Escalate an enquiry to a human agent.

    - **reason**: Why this enquiry is being escalated.
    - Already-escalated enquiries return a 400.

    **Example request body:**
    ```json
    {
      "reason": "Customer is unresponsive and the issue is time-sensitive."
    }
    ```
    """
    enquiry: Enquiry | None = db.query(Enquiry).filter(Enquiry.id == id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found.")
    if enquiry.status == EnquiryStatus.ESCALATED:
        raise HTTPException(status_code=400, detail="Enquiry is already escalated.")

    enquiry.status = EnquiryStatus.ESCALATED
    enquiry.escalation_reason = payload.reason
    db.commit()

    _log_event(db, id, "escalated", f"Manual escalation. Reason: {payload.reason}")

    logger.info(json.dumps({
        "event": "escalation_triggered",
        "enquiry_id": id,
        "reason": payload.reason,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }))

    return {
        "message": "Enquiry escalated to human agent.",
        "enquiry_id": id,
        "reason": payload.reason,
    }


@app.get(
    "/enquiry/{id}/history",
    response_model=EnquiryOut,
    status_code=200,
    summary="Get full conversation history and status timeline",
    tags=["Enquiries"],
    responses={
        200: {"description": "Enquiry detail with status timeline."},
        404: {"description": "Enquiry not found."},
    },
)
def get_history(id: str, db: Session = Depends(get_db)):
    """
    Retrieve the full conversation history and status timeline for an enquiry.

    Returns the enquiry record plus all events in chronological order.
    """
    enquiry: Enquiry | None = db.query(Enquiry).filter(Enquiry.id == id).first()
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
    status_code=200,
    summary="Health check  API and database status",
    tags=["System"],
)
def health_check(db: Session = Depends(get_db)):
    """
    Returns:
    - **status**: Always `ok` if the API is running.
    - **database**: `connected` or an error message.
    - **app**: Application name from config.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc}"

    return HealthResponse(
        status="ok",
        database=db_status,
        app=settings.APP_NAME,
    )
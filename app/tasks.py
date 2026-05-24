"""
Background task: SOP matching logic.

Runs after every new enquiry via FastAPI BackgroundTasks.
Matches inbound message to one of 5 hardcoded SOPs using keyword logic.
If no SOP matches, auto-escalates and logs the event.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Enquiry, EnquiryEvent, EnquiryStatus


# ── Structured JSON logging ───────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        }
        return json.dumps(payload)


def _build_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JSONFormatter())
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return log


logger = _build_logger(__name__)


# ── SOP definitions ───────────────────────────────────────────────────────────
# Each SOP: list of trigger keywords + a suggested response template.

SOPS: dict[str, dict] = {
    "booking_enquiry": {
        "keywords": ["book", "appointment", "schedule", "reserve", "slot", "availability"],
        "response": (
            "Thank you for reaching out! We'd be happy to help you schedule an appointment. "
            "Please share your preferred date, time, and location and our team will confirm."
        ),
    },
    "pricing_question": {
        "keywords": ["price", "cost", "fee", "charge", "quote", "pricing", "how much", "rates", "package"],
        "response": (
            "Thanks for your interest! We offer flexible pricing based on your requirements. "
            "Our team will send a detailed quote within 24 hours."
        ),
    },
    "complaint": {
        "keywords": [
            "complaint", "issue", "problem", "unhappy", "dissatisfied",
            "bad", "wrong", "error", "not working", "broken", "refund",
        ],
        "response": (
            "We sincerely apologise for the inconvenience. Your complaint has been logged "
            "and a senior support agent will reach out within 2 business hours."
        ),
    },
    "after_hours": {
        "keywords": [
            "closed", "after hours", "night", "weekend", "holiday",
            "not available", "out of office", "off hours",
        ],
        "response": (
            "Thank you for contacting us. We are currently outside business hours (Mon–Fri, 9am–6pm IST). "
            "Your enquiry has been logged and we will respond on the next business day."
        ),
    },
    "general_support": {
        "keywords": [
            "help", "support", "assist", "information", "info",
            "question", "query", "how do i", "how to", "contact",
        ],
        "response": (
            "Thank you for getting in touch! Our support team has received your message "
            "and will get back to you within 4 business hours."
        ),
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match_sop(message: str) -> tuple[str | None, str | None]:
    """Return (sop_name, suggested_response) or (None, None)."""
    msg_lower = message.lower()
    for sop_name, sop_data in SOPS.items():
        for keyword in sop_data["keywords"]:
            if keyword in msg_lower:
                return sop_name, sop_data["response"]
    return None, None


def _log_event(db: Session, enquiry_id: str, event_type: str, detail: str | None = None) -> None:
    """Append an immutable event to the enquiry timeline."""
    event = EnquiryEvent(
        enquiry_id=enquiry_id,
        event_type=event_type,
        detail=detail,
    )
    db.add(event)
    db.commit()


# ── Main background task ──────────────────────────────────────────────────────

def process_enquiry(enquiry_id: str) -> None:
    """
    Background task entry point.
    1. Load enquiry.
    2. Mark as PROCESSING.
    3. Run SOP keyword match.
    4. Update status to SOP_MATCHED or ESCALATED.
    5. Log structured events throughout.
    """
    logger.info(json.dumps({"event": "task_started", "enquiry_id": enquiry_id}))

    db = SessionLocal()
    try:
        enquiry: Enquiry | None = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()

        if not enquiry:
            logger.error(json.dumps({
                "event": "task_error",
                "enquiry_id": enquiry_id,
                "reason": "Enquiry record not found in DB.",
            }))
            return

        # ── Step 1: mark processing ───────────────────────────────────────────────
        enquiry.status = EnquiryStatus.PROCESSING
        db.commit()

        # ── Step 2: SOP match ─────────────────────────────────────────────────────
        sop_name, suggested_response = _match_sop(enquiry.message)

        if sop_name:
            enquiry.matched_sop = sop_name
            enquiry.suggested_response = suggested_response
            enquiry.status = EnquiryStatus.SOP_MATCHED
            db.commit()

            _log_event(db, enquiry_id, "sop_matched", f"Matched SOP: {sop_name}")
            logger.info(json.dumps({
                "event": "sop_matched",
                "enquiry_id": enquiry_id,
                "sop": sop_name,
            }))

        else:
            # ── Step 3: auto-escalate if no SOP matches ───────────────────────────
            enquiry.status = EnquiryStatus.ESCALATED
            enquiry.escalation_reason = "No SOP matched for inbound message. Flagged for human review."
            db.commit()

            _log_event(
                db, enquiry_id, "auto_escalated",
                "No SOP matched. Enquiry escalated to human agent automatically.",
            )
            logger.warning(json.dumps({
                "event": "escalation_triggered",
                "enquiry_id": enquiry_id,
                "reason": "No SOP matched",
            }))

        logger.info(json.dumps({
            "event": "task_completed",
            "enquiry_id": enquiry_id,
            "final_status": enquiry.status,
        }))
    finally:
        db.close()
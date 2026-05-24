"""
Closira Backend - SOP Automation Task

Processes raw text payloads in background loops to isolate intent, match predefined 
response rule sets, or flag exceptional inputs for human review.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Enquiry, EnquiryEvent, EnquiryStatus

logger = logging.getLogger(__name__)


# ── Automation Routing Rules ──────────────────────────────────────────────────

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


# ── Pipeline Utilities ────────────────────────────────────────────────────────

def _match_sop(message: str) -> tuple[str | None, str | None]:
    """Scans clean input string text against hardcoded signature phrases."""
    msg_lower = message.lower()
    for sop_name, sop_data in SOPS.items():
        if any(keyword in msg_lower for keyword in sop_data["keywords"]):
            return sop_name, sop_data["response"]
    return None, None


def _log_event(db: Session, enquiry_id: str, event_type: str, detail: str | None = None) -> None:
    """Commits an immutable timeline entry tracking internal status progression."""
    event = EnquiryEvent(
        enquiry_id=enquiry_id,
        event_type=event_type,
        detail=detail,
    )
    db.add(event)
    db.commit()


# ── Background Execution Engine ───────────────────────────────────────────────

def process_enquiry(enquiry_id: str) -> None:
    """
    Main ingestion execution worker pipeline task.
    """
    logger.info(json.dumps({"event": "task_started", "enquiry_id": enquiry_id}))

    db = SessionLocal()
    try:
        enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
        if not enquiry:
            logger.error(
                json.dumps({
                    "event": "task_error",
                    "enquiry_id": enquiry_id,
                    "reason": "Enquiry target record missing from storage engine layer.",
                })
            )
            return

        # Advance state to active processing loop
        enquiry.status = EnquiryStatus.PROCESSING
        db.commit()

        sop_name, suggested_response = _match_sop(enquiry.message)

        if sop_name:
            enquiry.matched_sop = sop_name
            enquiry.suggested_response = suggested_response
            enquiry.status = EnquiryStatus.SOP_MATCHED
            db.commit()

            _log_event(db, enquiry_id, "sop_matched", f"Matched automated track: {sop_name}")
            
            logger.info(
                json.dumps({
                    "event": "sop_matched",
                    "enquiry_id": enquiry_id,
                    "sop": sop_name,
                })
            )
        else:
            # Drop through to immediate agent alert escalation pool on match failure
            enquiry.status = EnquiryStatus.ESCALATED
            enquiry.escalation_reason = "No matching customer communication SOP signature found."
            db.commit()

            _log_event(
                db, enquiry_id, "auto_escalated",
                "Fallback mechanism: escalated automatically due to missing intent matching rule context.",
            )
            
            logger.warning(
                json.dumps({
                    "event": "escalation_triggered",
                    "enquiry_id": enquiry_id,
                    "reason": "unmatched_intent_payload",
                })
            )

        logger.info(
            json.dumps({
                "event": "task_completed",
                "enquiry_id": enquiry_id,
                "final_status": enquiry.status,
            })
        )
        
    finally:
        db.close()
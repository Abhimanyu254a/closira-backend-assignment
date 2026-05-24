import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.database import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class EnquiryStatus(str, enum.Enum):
    OPEN = "open"
    PROCESSING = "processing"
    SOP_MATCHED = "sop_matched"
    FOLLOW_UP_SCHEDULED = "follow_up_scheduled"
    ESCALATED = "escalated"
    CLOSED = "closed"


class Channel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CALL = "call"


# ── Tables ───────────────────────────────────────────────────────────────────

class Enquiry(Base):
    """Core enquiry record. One row per inbound customer message."""
    __tablename__ = "enquiries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_name = Column(String(255), nullable=False)
    channel = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default=EnquiryStatus.OPEN, nullable=False)

    # Set by background SOP-matching task
    matched_sop = Column(String(100), nullable=True)
    suggested_response = Column(Text, nullable=True)

    # Set on manual or auto escalation
    escalation_reason = Column(Text, nullable=True)

    # Set when follow-up is scheduled
    follow_up_delay_minutes = Column(String(20), nullable=True)
    follow_up_message_template = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class EnquiryEvent(Base):
    """
    Append-only event log for every state change on an Enquiry.
    Serves as the status timeline returned by GET /enquiry/{id}/history.
    """
    __tablename__ = "enquiry_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    enquiry_id = Column(String, ForeignKey("enquiries.id"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)   # e.g. "created", "sop_matched"
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

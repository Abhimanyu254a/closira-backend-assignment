import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from app.database import Base


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


class Enquiry(Base):
    __tablename__ = "enquiries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_name = Column(String(255), nullable=False)
    channel = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default=EnquiryStatus.OPEN, nullable=False)

    # Automation fields
    matched_sop = Column(String(100), nullable=True)
    suggested_response = Column(Text, nullable=True)

    # State override fields
    escalation_reason = Column(Text, nullable=True)
    follow_up_delay_minutes = Column(String(20), nullable=True)
    follow_up_message_template = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )


class EnquiryEvent(Base):
    __tablename__ = "enquiry_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    enquiry_id = Column(String, ForeignKey("enquiries.id"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)  # e.g., "created", "sop_matched"
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
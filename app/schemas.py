from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models import Channel


# ── Request bodies ────────────────────────────────────────────────────────────

class EnquiryCreate(BaseModel):
    channel: Channel = Field(..., example="whatsapp")
    customer_name: str = Field(..., min_length=1, max_length=255, example="Rahul Sharma")
    message: str = Field(..., min_length=1, example="Hi, I'd like to book an appointment.")

    model_config = {"use_enum_values": True}


class FollowUpRequest(BaseModel):
    delay_minutes: int = Field(..., ge=1, le=10080, example=30,
                               description="Delay in minutes before the follow-up is sent (max 1 week).")
    message_template: Optional[str] = Field(
        None,
        example="Hi {customer_name}, just following up on your enquiry.",
        description="Optional message template. Use {customer_name} as a placeholder.",
    )


class EscalateRequest(BaseModel):
    reason: str = Field(..., min_length=1, example="Customer requested to speak to a human agent.")


# ── Response bodies ───────────────────────────────────────────────────────────

class EnquiryCreatedResponse(BaseModel):
    job_id: str = Field(..., example="3f1c2d4e-...")
    message: str = Field(default="Enquiry received. Processing in background.")


class EnquiryEventOut(BaseModel):
    id: str
    event_type: str
    detail: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class EnquiryOut(BaseModel):
    id: str
    customer_name: str
    channel: str
    message: str
    status: str
    matched_sop: Optional[str]
    suggested_response: Optional[str]
    escalation_reason: Optional[str]
    follow_up_delay_minutes: Optional[str]
    follow_up_message_template: Optional[str]
    created_at: datetime
    updated_at: datetime
    events: List[EnquiryEventOut] = []

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str = Field(example="ok")
    database: str = Field(example="connected")
    app: str = Field(example="Closira Backend")
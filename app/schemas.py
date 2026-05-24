from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models import Channel


class EnquiryCreate(BaseModel):
    channel: Channel = Field(..., json_schema_extra={"example": "whatsapp"})
    customer_name: str = Field(..., min_length=1, max_length=255, json_schema_extra={"example": "Rahul Sharma"})
    message: str = Field(..., min_length=1, json_schema_extra={"example": "Hi, I'd like to book an appointment."})

    model_config = {"use_enum_values": True}


class FollowUpRequest(BaseModel):
    delay_minutes: int = Field(..., ge=1, le=10080, json_schema_extra={"example": 30})
    message_template: Optional[str] = Field(None, json_schema_extra={"example": "Hi {customer_name}, just following up."})


class EscalateRequest(BaseModel):
    reason: str = Field(..., min_length=1, json_schema_extra={"example": "Customer requested human agent."})


class EnquiryCreatedResponse(BaseModel):
    job_id: str = Field(..., json_schema_extra={"example": "3f1c2d4e-b5a1-4f9e-8c3d-2b1a0c9d8e7f"})
    message: str = "Enquiry received. Processing in background."


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
    status: str = Field(..., json_schema_extra={"example": "ok"})
    database: str = Field(..., json_schema_extra={"example": "connected"})
    app: str = Field(..., json_schema_extra={"example": "Closira Backend"})
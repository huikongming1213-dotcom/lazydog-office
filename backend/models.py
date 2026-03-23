from sqlalchemy import Column, String, Float, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from backend.database import Base
import uuid


def gen_uuid():
    return str(uuid.uuid4())


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=gen_uuid)
    status = Column(String, default="pending")
    # pending | running | pending_approval | approved | rejected | revision_requested | completed | failed
    topic = Column(String, nullable=False)
    platform_list = Column(JSON, default=list)
    tone = Column(String, default="casual")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # N8N integration
    n8n_resume_url = Column(String, nullable=True)   # N8N Wait Webhook URL to resume flow
    approval_status = Column(String, nullable=True)   # pending_approval / approved / rejected / revision_requested

    # Results stored as JSON
    trend_result = Column(JSON, nullable=True)
    copy_result = Column(JSON, nullable=True)
    image_result = Column(JSON, nullable=True)
    supervisor_result = Column(JSON, nullable=True)

    # Revision tracking
    revision_notes = Column(Text, nullable=True)


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    job_id = Column(String, nullable=False, index=True)
    agent_name = Column(String, nullable=False)
    action = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    level = Column(String, default="info")   # info | error | warning
    timestamp = Column(DateTime, server_default=func.now())


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=gen_uuid)
    job_id = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)   # ig | linkedin | x | threads | fb
    caption = Column(Text, nullable=True)
    hashtags = Column(JSON, default=list)
    image_url = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    status = Column(String, default="draft")   # draft | scheduled | published | failed
    created_at = Column(DateTime, server_default=func.now())

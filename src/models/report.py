"""Report model - generated reports."""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.models.base import Base


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    report_type = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    generated_by = Column(Integer, ForeignKey("users.id"))

    session = relationship("Session", back_populates="reports")
    teacher = relationship("User", back_populates="reports")

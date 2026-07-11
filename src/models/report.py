"""Report model - generated reports."""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
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
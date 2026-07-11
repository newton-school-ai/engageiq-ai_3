"""Nudge model - nudge history and effectiveness."""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from src.models.base import Base

class Nudge(Base):
    __tablename__ = "nudges"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    nudge_type = Column(String, nullable=False) 
    message = Column(String, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    was_effective = Column(Boolean, default=None)  

    # Relationships
    session = relationship("Session", back_populates="nudges")
    student = relationship("User", back_populates="nudges")

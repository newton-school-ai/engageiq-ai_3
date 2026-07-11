"""EngagementLog model - per-frame engagement data."""

from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from src.models.base import Base

class EngagementLog(Base):
    __tablename__ = "engagement_logs"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    eng_score = Column(Float, nullable=False)
    eng_state = Column(String, nullable=False)  
    gaze = Column(String)                   
    drowsiness = Column(Float, default=0.0)
    expression = Column(String)   

    session = relationship("Session", back_populates="engagement_logs")
    student = relationship("User", back_populates="engagement_logs")

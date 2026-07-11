"""Session model - lecture sessions."""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from src.models.base import Base

class Session(Base):
    __tablename__= "sessions"
    
    id = Column(Integer,primary_key=True)
    title=Column(String, nullable=False)
    course_id=Column(Integer,ForeignKey("courses.id"), nullable=False)
    teacher_id=Column(Integer,ForeignKey("users.id"), nullable=False)
    started_at=Column(DateTime, default=datetime.utcnow)
    ended_at=Column(DateTime, nullable=True)
    avg_engagement_score=Column(Float, default=0.0)

    course = relationship("Course", back_populates="sessions")
    teacher = relationship("User", back_populates="sessions")
    engagement_logs = relationship("EngagementLog", back_populates="session")
    nudges = relationship("Nudge", back_populates="session")        
    reports = relationship("Report", back_populates="session")     

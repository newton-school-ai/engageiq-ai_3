"""User model - student/teacher roles and privacy preferences."""

from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from src.models.base import Base

class UserRole(enum.Enum):
    student="student"
    teacher="teacher"
class User(Base):
    __tablename__ = "users"
    id = Column(Integer,primary_key=True)
    name = Column(String,nullable=False)
    email=Column(String,nullable=False,unique=True)
    role=Column(Enum(UserRole), nullable=False)
    privacy_consent= Column(Boolean, default=False)
    created_at= Column(DateTime, default=datetime.utcnow)

    sessions = relationship("Session", back_populates="teacher")
    courses = relationship("Course", back_populates="teacher")
    engagement_logs = relationship("EngagementLog", back_populates="student")
    nudges = relationship("Nudge", back_populates="student")
    reports = relationship("Report", back_populates="teacher")



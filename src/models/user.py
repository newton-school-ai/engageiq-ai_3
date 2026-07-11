"""User model - student/teacher roles and privacy preferences."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship

from src.models.base import Base


class UserRole(enum.Enum):
    student = "student"
    teacher = "teacher"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    role = Column(Enum(UserRole), nullable=False)
    privacy_consent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("Session", back_populates="teacher")
    courses = relationship("Course", back_populates="teacher")
    engagement_logs = relationship("EngagementLog", back_populates="student")
    nudges = relationship("Nudge", back_populates="student")
    reports = relationship("Report", back_populates="teacher")

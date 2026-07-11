"""Course model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.models.base import Base


class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    desc = Column(String)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    teacher = relationship("User", back_populates="courses")
    sessions = relationship("Session", back_populates="course")

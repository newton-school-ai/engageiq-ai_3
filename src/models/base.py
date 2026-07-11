"""SQLAlchemy base model."""

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, DateTime
from datetime import datetime

class Base(DeclarativeBase):
    pass

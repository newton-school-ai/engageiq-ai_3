"""SQLAlchemy base model."""

from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

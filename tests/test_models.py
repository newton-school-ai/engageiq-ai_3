"""Model tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.models.base import Base
from src.models import User, Course
from src.models.user import UserRole

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/engageiq_dev"
engine = create_engine(DATABASE_URL)

def test_create_user():
    with Session(engine) as db:
        user = User(name="UserA", email="test111@test.com", role=UserRole.student, privacy_consent=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        assert user.id is not None
        assert user.name == "UserA"
        print("✅ User creation test passed")
def test_course_teacher_relationship():
        with Session(engine) as db:
            teacher = User(name="TeacherA", email="teacher111@test.com", role=UserRole.teacher, privacy_consent=True)
            db.add(teacher)
            db.commit()
            db.refresh(teacher)
            course = Course(title="Test Course", desc="Test", teacher_id=teacher.id)
            db.add(course)
            db.commit()
            db.refresh(course)
            assert course.teacher_id == teacher.id
            print("✅ Relationship test passed")

def test_unique_email():
    with Session(engine) as db:
        with pytest.raises(Exception):
            u1 = User(name="A", email="same@test.com", role=UserRole.student, privacy_consent=True)
            u2 = User(name="B", email="same@test.com", role=UserRole.student, privacy_consent=True)
            db.add_all([u1, u2])
            db.commit()
        print("✅ Constraint test passed")

"""Seed script - sample data for development."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.models import User, Course, Session as CourseSession, EngagementLog, Nudge, Report
from src.models.user import UserRole

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/engageiq_dev"
engine = create_engine(DATABASE_URL)

def seed():
    with Session(engine) as db:
        teacher_1 =User(name="Rahul", email="rahul@gmail.com", role=UserRole.teacher, privacy_consent=True)
        teacher_2 =User(name="Zalak", email="zalak@gmail.com", role=UserRole.teacher, privacy_consent=True)
        students = []
        for i in range(1, 11):
            student = User(
                name=f"Student {i}",
                email=f"student{i}@nst.com",
                role=UserRole.student,
                privacy_consent=True
            )
            students.append(student)

        db.add_all([teacher_1,teacher_2]+students)
        db.commit()
        db.refresh(teacher_1)  
        db.refresh(teacher_2)
        print("2 teachers, 10 students created")
        
        course_1 = Course(title="Math", desc="Basic Math", teacher_id=teacher_1.id)
        course_2 = Course(title="Science", desc="Environmental Science", teacher_id=teacher_2.id)
        course_3 = Course(title="English", desc="English and Grammar", teacher_id=teacher_1.id)
        course_4 = Course(title="Hindi", desc="Basic Hindi", teacher_id=teacher_2.id)

        db.add_all([course_1,course_2,course_3,course_4])
        db.commit()
        db.refresh(course_1)
        db.refresh(course_2)
        db.refresh(course_3)
        db.refresh(course_4)

        print("4 courses created")

        print("Seed complete!")
if __name__ == "__main__":
    seed()



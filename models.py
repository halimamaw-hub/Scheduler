from datetime import datetime, time as dtime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    units = db.Column(db.Float, nullable=False, default=1.0)
    color = db.Column(db.String(7), nullable=False, default="#4f46e5")


class Week(db.Model):
    __tablename__ = "weeks"
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)  # Monday of that week
    day_start = db.Column(db.Time, nullable=False, default=dtime(7, 0))
    day_end = db.Column(db.Time, nullable=False, default=dtime(22, 0))
    max_hours_per_day = db.Column(db.Float, nullable=False, default=3.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sessions = db.relationship(
        "ClassSession", backref="week", cascade="all, delete-orphan"
    )
    overrides = db.relationship(
        "HourOverride", backref="week", cascade="all, delete-orphan"
    )
    slots = db.relationship(
        "StudySlot", backref="week", cascade="all, delete-orphan"
    )


class ClassSession(db.Model):
    """A block of time that is NOT available for studying that week
    (an actual lecture, recitation, or make-up class)."""

    __tablename__ = "class_sessions"
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey("weeks.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday ... 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    note = db.Column(db.String(200))

    subject = db.relationship("Subject")


class HourOverride(db.Model):
    """Per-week override of how many hours a subject needs
    (default is units * 3)."""

    __tablename__ = "hour_overrides"
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey("weeks.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    hours = db.Column(db.Float, nullable=False)

    subject = db.relationship("Subject")


class StudySlot(db.Model):
    """One generated 1-hour study block. A 15-minute break is implied
    immediately after end_time."""

    __tablename__ = "study_slots"
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey("weeks.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    subject = db.relationship("Subject")

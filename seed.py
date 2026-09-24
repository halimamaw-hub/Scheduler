"""
One-time helper to pre-load your subjects and the class times you already
gave me. Run this ONCE after the app has started (so the tables exist):

    python seed.py

It creates:
  - Subjects: Torts, Property, Crimpro, Labor, Insurance, Sales
  - A Week starting the next Monday
  - Every class session you've given me an exact time for:
      Mon  Torts       9:00 - 10:30
      Mon  Property    1:00 -  3:00 PM
      Tue  Crimpro     9:30 - 11:00
      Tue  Labor       4:30 -  6:00 PM
      Wed  Torts       9:00 - 10:30
      Wed  Insurance   1:00 -  3:00 PM
      Thu  Property    1:00 -  3:00 PM
      Thu  Labor       4:30 -  6:00 PM
      Fri  Crimpro     9:30 - 11:00

Sales (Friday) is NOT added here -- you said its time keeps changing, so it
is deliberately left out. Add it yourself in the "Edit week" page each week
once you know that week's actual time; otherwise the ILP will treat that
slot as free and may schedule study time right on top of an actual class.
"""

from datetime import date, timedelta, time

from app import create_app
from models import db, Subject, Week, ClassSession

app = create_app()

with app.app_context():
    def get_or_create_subject(name, units, color):
        s = Subject.query.filter_by(name=name).first()
        if not s:
            s = Subject(name=name, units=units, color=color)
            db.session.add(s)
            db.session.commit()
        return s

    torts = get_or_create_subject("Torts", 1.5, "#ef4444")
    property_ = get_or_create_subject("Property", 2.0, "#f59e0b")
    crimpro = get_or_create_subject("Crimpro", 1.5, "#10b981")
    labor = get_or_create_subject("Labor", 1.5, "#3b82f6")
    insurance = get_or_create_subject("Insurance", 2.0, "#8b5cf6")
    sales = get_or_create_subject("Sales", 2.0, "#ec4899")

    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_ahead)

    week = Week.query.filter_by(start_date=start).first()
    if not week:
        week = Week(start_date=start)
        db.session.add(week)
        db.session.commit()

    def add_session(subject, day, start_t, end_t, note=None):
        exists = ClassSession.query.filter_by(
            week_id=week.id, subject_id=subject.id, day_of_week=day, start_time=start_t
        ).first()
        if not exists:
            db.session.add(
                ClassSession(
                    week_id=week.id,
                    subject_id=subject.id,
                    day_of_week=day,
                    start_time=start_t,
                    end_time=end_t,
                    note=note,
                )
            )

    add_session(torts, 0, time(9, 0), time(10, 30))         # Monday
    add_session(property_, 0, time(13, 0), time(15, 0))      # Monday
    add_session(crimpro, 1, time(9, 30), time(11, 0))        # Tuesday
    add_session(labor, 1, time(16, 30), time(18, 0))         # Tuesday
    add_session(torts, 2, time(9, 0), time(10, 30))          # Wednesday
    add_session(insurance, 2, time(13, 0), time(15, 0))       # Wednesday
    add_session(property_, 3, time(13, 0), time(15, 0))       # Thursday
    add_session(labor, 3, time(16, 30), time(18, 0))          # Thursday
    add_session(crimpro, 4, time(9, 30), time(11, 0))         # Friday

    db.session.commit()
    print(f"Seeded subjects and Week of {start} (id={week.id}).")
    print("Every session is in except Sales (Friday) -- its time keeps changing, "
          "so add it yourself on the 'Edit week' page once you know that week's "
          "time, then click 'Generate study schedule'.")

import os
from datetime import date, timedelta, time as dtime

from flask import Flask, render_template, request, redirect, url_for, flash

from models import db, Subject, Week, ClassSession, HourOverride, StudySlot
from scheduler import solve_schedule, DAYS, _to_time


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    db_url = os.environ.get("DATABASE_URL", "sqlite:///study.db")
    # Render/Heroku-style URLs sometimes start with postgres:// which
    # SQLAlchemy 2.x no longer accepts.
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    with app.app_context():
        db.create_all()

    app.jinja_env.globals["enumerate"] = enumerate

    register_routes(app)
    return app


def register_routes(app):
    @app.route("/")
    def index():
        weeks = Week.query.order_by(Week.start_date.desc()).all()
        return render_template("index.html", weeks=weeks)

    @app.route("/subjects", methods=["GET", "POST"])
    def subjects():
        if request.method == "POST":
            name = request.form["name"].strip()
            units = float(request.form["units"])
            color = request.form.get("color") or "#4f46e5"
            if name:
                db.session.add(Subject(name=name, units=units, color=color))
                db.session.commit()
            return redirect(url_for("subjects"))
        subs = Subject.query.order_by(Subject.name).all()
        return render_template("subjects.html", subjects=subs)

    @app.route("/subjects/<int:sid>/delete", methods=["POST"])
    def delete_subject(sid):
        s = Subject.query.get_or_404(sid)
        db.session.delete(s)
        db.session.commit()
        return redirect(url_for("subjects"))

    @app.route("/week/new", methods=["POST"])
    def new_week():
        latest = Week.query.order_by(Week.start_date.desc()).first()
        if latest:
            start = latest.start_date + timedelta(days=7)
        else:
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7 or 7
            start = today + timedelta(days=days_ahead)

        week = Week(start_date=start)
        if latest:
            week.day_start = latest.day_start
            week.day_end = latest.day_end
            week.max_hours_per_day = latest.max_hours_per_day
        db.session.add(week)
        db.session.commit()

        # Copy last week's class sessions and hour overrides as a starting
        # template -- this is the "edit every Saturday" workflow: everything
        # carries over, then you tweak whatever moved (make-up classes,
        # exam-week hour bumps, etc).
        if latest:
            for sess in latest.sessions:
                db.session.add(
                    ClassSession(
                        week_id=week.id,
                        subject_id=sess.subject_id,
                        day_of_week=sess.day_of_week,
                        start_time=sess.start_time,
                        end_time=sess.end_time,
                        note=sess.note,
                    )
                )
            for ov in latest.overrides:
                db.session.add(
                    HourOverride(week_id=week.id, subject_id=ov.subject_id, hours=ov.hours)
                )
            db.session.commit()

        return redirect(url_for("edit_week", week_id=week.id))

    @app.route("/week/<int:week_id>/delete", methods=["POST"])
    def delete_week(week_id):
        w = Week.query.get_or_404(week_id)
        db.session.delete(w)
        db.session.commit()
        return redirect(url_for("index"))

    @app.route("/week/<int:week_id>/edit", methods=["GET", "POST"])
    def edit_week(week_id):
        week = Week.query.get_or_404(week_id)
        subjects_list = Subject.query.order_by(Subject.name).all()

        if request.method == "POST":
            form_type = request.form.get("form_type")

            if form_type == "settings":
                week.day_start = dtime.fromisoformat(request.form["day_start"])
                week.day_end = dtime.fromisoformat(request.form["day_end"])
                week.max_hours_per_day = float(request.form["max_hours_per_day"])
                db.session.commit()

            elif form_type == "session":
                db.session.add(
                    ClassSession(
                        week_id=week.id,
                        subject_id=int(request.form["subject_id"]),
                        day_of_week=int(request.form["day_of_week"]),
                        start_time=dtime.fromisoformat(request.form["start_time"]),
                        end_time=dtime.fromisoformat(request.form["end_time"]),
                        note=request.form.get("note") or None,
                    )
                )
                db.session.commit()

            elif form_type == "override":
                subject_id = int(request.form["subject_id"])
                hours = float(request.form["hours"])
                ov = HourOverride.query.filter_by(
                    week_id=week.id, subject_id=subject_id
                ).first()
                if ov:
                    ov.hours = hours
                else:
                    db.session.add(
                        HourOverride(week_id=week.id, subject_id=subject_id, hours=hours)
                    )
                db.session.commit()

            return redirect(url_for("edit_week", week_id=week.id))

        overrides = {ov.subject_id: ov.hours for ov in week.overrides}
        required = {s.id: overrides.get(s.id, s.units * 3) for s in subjects_list}

        sessions_by_day = {i: [] for i in range(7)}
        for sess in week.sessions:
            sessions_by_day[sess.day_of_week].append(sess)
        for d in sessions_by_day:
            sessions_by_day[d].sort(key=lambda s: s.start_time)

        return render_template(
            "week_edit.html",
            week=week,
            subjects=subjects_list,
            required=required,
            overrides=overrides,
            sessions_by_day=sessions_by_day,
            DAYS=DAYS,
        )

    @app.route("/week/<int:week_id>/session/<int:sess_id>/delete", methods=["POST"])
    def delete_session(week_id, sess_id):
        sess = ClassSession.query.get_or_404(sess_id)
        db.session.delete(sess)
        db.session.commit()
        return redirect(url_for("edit_week", week_id=week_id))

    @app.route("/week/<int:week_id>/generate", methods=["POST"])
    def generate(week_id):
        week = Week.query.get_or_404(week_id)
        subjects_list = Subject.query.order_by(Subject.name).all()
        overrides = {ov.subject_id: ov.hours for ov in week.overrides}
        required = {s.id: overrides.get(s.id, s.units * 3) for s in subjects_list}

        sessions_by_day = {i: [] for i in range(7)}
        for sess in week.sessions:
            sessions_by_day[sess.day_of_week].append((sess.start_time, sess.end_time))

        assignments, shortfalls = solve_schedule(
            subjects_list, required, week, sessions_by_day
        )

        StudySlot.query.filter_by(week_id=week.id).delete()
        for a in assignments:
            db.session.add(
                StudySlot(
                    week_id=week.id,
                    subject_id=a["subject_id"],
                    day_of_week=a["day"],
                    start_time=_to_time(a["start"]),
                    end_time=_to_time(a["end"]),
                )
            )
        db.session.commit()

        short_msgs = []
        for sid, hrs in shortfalls.items():
            if hrs and hrs > 0.1:
                subj = Subject.query.get(sid)
                short_msgs.append(f"{subj.name}: short by {round(hrs, 2)}h")
        if short_msgs:
            flash(
                "Generated, but there wasn't enough free time for everything -- "
                + "; ".join(short_msgs)
            )
        else:
            flash("Schedule generated.")

        return redirect(url_for("view_week", week_id=week.id))

    @app.route("/week/<int:week_id>")
    def view_week(week_id):
        week = Week.query.get_or_404(week_id)

        timeline_by_day = {i: [] for i in range(7)}
        for sess in week.sessions:
            timeline_by_day[sess.day_of_week].append(
                {
                    "start": sess.start_time,
                    "end": sess.end_time,
                    "kind": "class",
                    "subject": sess.subject,
                    "note": sess.note,
                }
            )
        for slot in week.slots:
            timeline_by_day[slot.day_of_week].append(
                {
                    "start": slot.start_time,
                    "end": slot.end_time,
                    "kind": "study",
                    "subject": slot.subject,
                    "note": None,
                }
            )
        for d in range(7):
            timeline_by_day[d].sort(key=lambda item: item["start"])

        return render_template(
            "week_view.html",
            week=week,
            DAYS=DAYS,
            timeline_by_day=timeline_by_day,
        )


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)

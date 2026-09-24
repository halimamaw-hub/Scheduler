"""
Integer Linear Program that decides WHEN (which hour, which day) to study
each subject so that:

  - every subject gets exactly its required weekly hours (units * 3,
    unless overridden), or as close as possible if the week is too full
  - study only happens inside free time (class sessions block time out)
  - every 1-hour study block is followed by a 15-minute break, enforced
    by only ever offering 75-minute (60 study + 15 break) slots
  - no subject is crammed into a single day beyond a configurable cap

Model
-----
Sets
  C = subjects
  S = all available 75-minute slots across the week (derived from the
      day's free windows, i.e. day_start/day_end minus class sessions)

Decision variables
  x[c, s] in {0, 1}      subject c is studied during slot s
  shortfall[c] >= 0      hours of subject c that could not be scheduled

Constraints
  sum_c x[c, s] <= 1                              for every slot s
  sum_s x[c, s] <= required_hours[c]               for every subject c
  sum_s x[c, s] + shortfall[c] >= required_hours[c]  for every subject c
  sum_{s in day d} x[c, s] <= max_hours_per_day     for every c, day d

Objective
  minimize sum_c shortfall[c]

(The two constraints on required_hours together force
 sum_s x[c,s] == required_hours[c] whenever that's feasible; any gap
 that's impossible to close because there isn't enough free time shows
 up as shortfall[c] instead of making the model infeasible.)
"""

from datetime import time as dtime

import pulp

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

SLOT_MINUTES = 75  # 60 minutes of study + 15 minute break
STUDY_MINUTES = 60


def _to_minutes(t: dtime) -> int:
    return t.hour * 60 + t.minute


def _to_time(m: float) -> dtime:
    m = int(round(m)) % (24 * 60)
    return dtime(hour=m // 60, minute=m % 60)


def build_free_windows(day_start: dtime, day_end: dtime, busy_intervals):
    """busy_intervals: list of (start_time, end_time) class sessions on one day.
    Returns list of (start_min, end_min) free windows within [day_start, day_end].
    """
    start_of_day = _to_minutes(day_start)
    end_of_day = _to_minutes(day_end)
    intervals = sorted(
        (_to_minutes(s), _to_minutes(e)) for s, e in busy_intervals if e > s
    )

    free = []
    cursor = start_of_day
    for s, e in intervals:
        s = max(s, start_of_day)
        e = min(e, end_of_day)
        if s >= end_of_day:
            continue
        if s > cursor:
            free.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < end_of_day:
        free.append((cursor, end_of_day))
    return [(s, e) for s, e in free if e - s >= STUDY_MINUTES]


def generate_slots(week, sessions_by_day):
    """Returns a flat list of dicts: {day, start, end} where 'end' is the
    end of the STUDY portion (start + 60 min); the 15-minute break that
    follows is implicit and not double-booked because the next slot
    never starts less than 75 minutes after this one."""
    slots = []
    end_of_day = _to_minutes(week.day_end)
    for day_idx in range(7):
        windows = build_free_windows(
            week.day_start, week.day_end, sessions_by_day.get(day_idx, [])
        )
        for w_start, w_end in windows:
            cursor = w_start
            while cursor + SLOT_MINUTES <= w_end:
                slots.append({"day": day_idx, "start": cursor, "end": cursor + STUDY_MINUTES})
                cursor += SLOT_MINUTES
            # Allow a final bare 60-minute slot (no trailing break needed)
            # only if it reaches exactly the end of the day's window.
            if cursor + STUDY_MINUTES == w_end:
                slots.append({"day": day_idx, "start": cursor, "end": cursor + STUDY_MINUTES})
    return slots


def solve_schedule(subjects, required_hours, week, sessions_by_day):
    """
    subjects: list of Subject model objects
    required_hours: dict {subject_id: hours_needed_this_week}
    week: Week model object (has day_start, day_end, max_hours_per_day)
    sessions_by_day: dict {day_of_week: [(start_time, end_time), ...]}

    Returns (assignments, shortfalls)
      assignments: list of {subject_id, day, start, end} (minutes)
      shortfalls: dict {subject_id: hours_not_scheduled}
    """
    slots = generate_slots(week, sessions_by_day)
    if not slots:
        return [], {c.id: required_hours.get(c.id, 0.0) for c in subjects}

    prob = pulp.LpProblem("study_schedule", pulp.LpMinimize)

    x = {
        (c.id, i): pulp.LpVariable(f"x_{c.id}_{i}", cat="Binary")
        for c in subjects
        for i in range(len(slots))
    }
    shortfall = {
        c.id: pulp.LpVariable(f"short_{c.id}", lowBound=0) for c in subjects
    }

    # A slot can only be used for one subject at a time.
    for i in range(len(slots)):
        prob += pulp.lpSum(x[(c.id, i)] for c in subjects) <= 1

    for c in subjects:
        req = required_hours.get(c.id, 0.0)
        total = pulp.lpSum(x[(c.id, i)] for i in range(len(slots)))
        prob += total <= req
        prob += total + shortfall[c.id] >= req

        for day_idx in range(7):
            day_slot_idxs = [i for i, s in enumerate(slots) if s["day"] == day_idx]
            if day_slot_idxs:
                prob += (
                    pulp.lpSum(x[(c.id, i)] for i in day_slot_idxs)
                    <= week.max_hours_per_day
                )

    prob += pulp.lpSum(shortfall[c.id] for c in subjects)

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    assignments = []
    for c in subjects:
        for i, slot in enumerate(slots):
            val = pulp.value(x[(c.id, i)])
            if val and val > 0.5:
                assignments.append(
                    {
                        "subject_id": c.id,
                        "day": slot["day"],
                        "start": slot["start"],
                        "end": slot["end"],
                    }
                )

    shortfalls = {c.id: (pulp.value(shortfall[c.id]) or 0.0) for c in subjects}
    return assignments, shortfalls

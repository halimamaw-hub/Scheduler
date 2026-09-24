# Study Scheduler

A small Flask app that uses an **Integer Linear Program (ILP)** to decide
which hour of your week you should study each subject, given your class
schedule.

## How the model works (`scheduler.py`)

- Every subject needs `units × 3` hours of study per week by default
  (editable per week).
- Your class times block out time that can't be used for studying.
- Whatever's left is chopped into 75-minute slots (60 min study + a
  mandatory 15-min break), so a break is baked into every study hour
  automatically — it's not something the solver can skip.
- The ILP then assigns subjects to slots so that:
  - no slot is double-booked,
  - every subject gets as close to its required hours as possible,
  - no subject is crammed into a single day beyond a cap you set
    (default 3h/day/subject), so hours actually spread across the week.
- If your free time genuinely isn't enough to fit everything, the model
  reports which subjects are short and by how much, instead of just
  failing.

It's solved with [PuLP](https://coin-or.github.io/pulp/) and the bundled
CBC solver — no external solver install needed.

## Weekly workflow

1. **First time only:** add your subjects on the *Subjects* page.
2. Every Saturday: click **"Plan next week"**. This copies last week's
   class sessions and hour overrides as a starting template.
3. Edit whatever changed — move a class that has a make-up session,
   delete a session, add a new one, bump a subject's hours up before an
   exam.
4. Click **Generate study schedule**.

## Running locally

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                 # http://localhost:5000
```

Optional: pre-load the subjects and class times you already gave me:

```bash
python seed.py
```

(It only added the three sessions where you gave exact times — Monday
Torts/Property, Tuesday Crimpro. Add the rest yourself in the UI.)

## Deploying: GitHub → Render

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create study-scheduler --public --source=. --push
# or push to an existing GitHub repo manually
```

On [Render](https://render.com):

1. New → Web Service → connect your GitHub repo.
2. Render will detect `render.yaml` automatically (or set manually):
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
3. Add environment variables (see next section for `DATABASE_URL`).
4. Deploy.

## The actual fix for "the website closes and I lose everything"

Two *different* things are happening on Render's free tier, and only one
of them is actually a problem:

**1. Spin-down (normal, not data loss).** A free web service goes to
sleep after ~15 minutes with no traffic. The next visit takes 30–60
seconds to "wake up." Annoying, but nothing is lost — it's just a cold
start. There's no free way around this on Render (a paid instance
type stays warm), so budget for that delay, or ping the URL periodically
with a free uptime monitor (e.g. UptimeRobot) if you want to avoid it.

**2. Ephemeral disk (this is the real problem).** Render's free web
services don't have a persistent disk. If the app writes data to a local
SQLite file, that file is **wiped on every restart/redeploy** — this is
almost certainly what's been eating your data, not the spin-down itself.
A screenshot works around it but obviously isn't a real fix.

**The fix:** point the app at an external database instead of a local
file, using the `DATABASE_URL` environment variable (already wired up in
`app.py` — it falls back to local SQLite only when `DATABASE_URL` isn't
set). Two free options that survive restarts and redeploys indefinitely:

- **[Neon](https://neon.tech)** — free Postgres, no expiry on the free tier.
- **[Supabase](https://supabase.com)** — free Postgres, also includes a UI to browse your data.

Steps:
1. Create a free Postgres database on either site.
2. Copy the connection string (`postgresql://user:pass@host/dbname`).
3. In Render → your service → Environment → add `DATABASE_URL` with that
   value.
4. Redeploy. From then on your subjects/weeks/schedules live in that
   database, independent of what Render's container does.

(Render also offers its own free Postgres, but on the free plan it
expires after 30 days — fine for testing, not for a semester.)

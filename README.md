# CareSync

Shared elderly care and medication management. One health profile, owned by the elderly person, shared with caretakers and family through secure passcode-based access.

> Status: feature-complete and deployable (Render + Supabase Postgres).

## Features so far

- **Smart Care Assistant (context-aware decisions):** a rule engine reads the situation (who is asking, time of day, today's doses, 7-day vs previous-week adherence, repeated misses at the same time slot, allergies vs medicine families, duplicate entries, courses ending, appointments in the next 48 h, pending approvals, care-circle setup) and returns prioritised suggestions (urgent → good news). Each suggestion is worded for the viewer's role and explains **why** it was shown. It is deterministic and fully unit-tested, and works with no AI key. Optional **OpenAI or Gemini** answers plain-language questions using a minimal, non-identifying context (no emails or codes) with strict safety instructions.

- **Profiles & passcode access:** the elder creates a profile and gets a 6-character Care Code. Members sign in with Care Code + email + personal passcode. Passcodes are salted PBKDF2 hashes; sessions are signed, httpOnly, SameSite=Strict cookies.
- **Roles:** `elder` (owner), `caretaker`, `family`, enforced on every endpoint. Membership is re-checked per request, so removing someone revokes access instantly.
- **Elder stays in control:** optional "approve caretaker changes" setting puts caretaker medication edits into a `pending` state until the elder approves.
- **Medications:** schedules with multiple daily times, start/end dates, pause/resume.
- **Doses:** today's checklist (`upcoming` / `due` / `overdue` / `taken` / `skipped`), idempotent dose logging, adherence % over N days.
- **Appointments:** CRUD with a one-click "Add to Google Calendar" link.
- **Activity log:** every change records who did what, and when.
- **Email reminders:** every 15 minutes a scheduled job (GitHub Actions → `POST /internal/run-reminders`, protected by a secret header) emails upcoming-dose reminders to the elder and caretakers, records doses not taken within 30 minutes as *missed* and alerts family and caretakers, and sends appointment reminders 24 h and 2 h before. Each notification is recorded so nothing is sent twice, failed sends are retried, rescheduled appointments get fresh reminders, and doses due before a medicine was added never count as missed. New members receive their sign-in details by email.
- **Elder-friendly web app:** large text with A / A+ / A++ sizing, high contrast, 48px+ touch targets, big "I took it" buttons, read-aloud of today's medicines, full keyboard support, skip link, screen-reader announcements and focus management. No build step: plain HTML, CSS and ES modules.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload        # in-memory database by default
# App: http://localhost:8000   API docs: http://localhost:8000/docs
python -m pytest                      # 137 tests (in-memory store)
TEST_DATABASE_URL=postgresql://... python -m pytest   # same suite on real Postgres
ruff check app tests
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `local`, `test` or `prod` | `local` |
| `SESSION_SECRET` | Cookie signing key (required in prod) | random per process |
| `DATABASE_URL` | PostgreSQL connection string (Supabase session pooler) | unset |
| `DB_BACKEND` | `memory`, `postgres` or `firestore` | `postgres` if `DATABASE_URL` is set, else `memory` |
| `GCP_PROJECT` | Google Cloud project id | from environment |
| `DOSE_GRACE_MINUTES` | Minutes before a dose counts as overdue | `30` |
| `OPENAI_API_KEY` | Optional: enables free-text questions via OpenAI (preferred if set) | unset |
| `OPENAI_MODEL` | OpenAI model id | `gpt-5.4-mini` |
| `GEMINI_API_KEY` | Optional: alternative AI provider (Google AI Studio key) | unset |
| `GEMINI_MODEL` | Gemini model id | `gemini-3.5-flash` |
| `SMTP_USER` / `SMTP_PASSWORD` | Gmail address and App Password for sending email | unset (emails logged, not sent) |
| `CRON_SECRET` | Shared secret the scheduler sends in `X-Cron-Secret` | unset (reminder endpoint disabled) |
| `APP_URL` | Public URL used in invite emails | `http://localhost:8000` |

## Project layout

```
app/
  main.py          app factory, security headers
  config.py        settings from environment
  security.py      passcode hashing, sessions, rate limiting
  deps.py          auth + role guards
  schemas.py       validated request models
  db/              repository interface; Postgres, Firestore and in-memory implementations
  services/        assistant (decision engine), reminders + emailer, ai (OpenAI / Gemini), schedule/adherence, audit log, calendar links
  routers/         auth, members, medications, doses, appointments, activity
static/            web app: index.html, styles.css, app.js (router), js/ (api, dom, views)
.github/workflows CI (lint + tests on every push) and the 15-minute reminder scheduler
tests/             pytest suite (in-memory DB, frozen clock, front-end safety checks)
```

## Deploy (Render + Supabase)

1. **Database:** a Supabase Postgres project with the `documents` table (the app also creates it on start). Row-level security is enabled with no policies, so Supabase's public API cannot read data; only the server connection can. Copy the **Session pooler** connection string from Supabase → *Connect*.
2. **Web service:** on Render, *New → Blueprint* and pick this repo. `render.yaml` builds the `Dockerfile` (Python 3.12, non-root user), checks `/healthz`, and generates `SESSION_SECRET` and `CRON_SECRET`. Enter `DATABASE_URL`, `APP_URL` (the Render URL), and optionally `OPENAI_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`.
3. **Reminders:** in GitHub → *Settings → Secrets and variables → Actions*, add variable `CARESYNC_URL` (the Render URL) and secret `CRON_SECRET` (same value as on Render). `.github/workflows/reminders.yml` then runs every 15 minutes.

In production the API docs are disabled, cookies are `Secure; HttpOnly; SameSite=Strict`, HSTS is on, and every secret comes from the environment.

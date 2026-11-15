# CareSync

Shared elderly care and medication management. One health profile, owned by the elderly person, shared with caretakers and family through secure passcode-based access.

> Status: core platform, accessible web app and Smart Care Assistant complete. Email reminders and deployment follow.

## Features so far

- **Smart Care Assistant (context-aware decisions):** a rule engine reads the situation (who is asking, time of day, today's doses, 7-day vs previous-week adherence, repeated misses at the same time slot, allergies vs medicine families, duplicate entries, courses ending, appointments in the next 48 h, pending approvals, care-circle setup) and returns prioritised suggestions (urgent → good news). Each suggestion is worded for the viewer's role and explains **why** it was shown. It is deterministic and fully unit-tested, and works with no AI key. Optional **Gemini** answers plain-language questions using a minimal, non-identifying context (no emails or codes) with strict safety instructions.

- **Profiles & passcode access:** the elder creates a profile and gets a 6-character Care Code. Members sign in with Care Code + email + personal passcode. Passcodes are salted PBKDF2 hashes; sessions are signed, httpOnly, SameSite=Strict cookies.
- **Roles:** `elder` (owner), `caretaker`, `family`, enforced on every endpoint. Membership is re-checked per request, so removing someone revokes access instantly.
- **Elder stays in control:** optional "approve caretaker changes" setting puts caretaker medication edits into a `pending` state until the elder approves.
- **Medications:** schedules with multiple daily times, start/end dates, pause/resume.
- **Doses:** today's checklist (`upcoming` / `due` / `overdue` / `taken` / `skipped`), idempotent dose logging, adherence % over N days.
- **Appointments:** CRUD with a one-click "Add to Google Calendar" link.
- **Activity log:** every change records who did what, and when.
- **Elder-friendly web app:** large text with A / A+ / A++ sizing, high contrast, 48px+ touch targets, big "I took it" buttons, read-aloud of today's medicines, full keyboard support, skip link, screen-reader announcements and focus management. No build step: plain HTML, CSS and ES modules.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload        # in-memory database by default
# App: http://localhost:8000   API docs: http://localhost:8000/docs
python -m pytest                      # 104 tests
ruff check app tests
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `local`, `test` or `prod` | `local` |
| `SESSION_SECRET` | Cookie signing key (required in prod) | random per process |
| `DB_BACKEND` | `memory` or `firestore` | `firestore` in prod |
| `GCP_PROJECT` | Google Cloud project id | from environment |
| `DOSE_GRACE_MINUTES` | Minutes before a dose counts as overdue | `30` |
| `GEMINI_API_KEY` | Optional: enables free-text questions (Google AI Studio key) | unset |
| `GEMINI_MODEL` | Gemini model id | `gemini-3.5-flash` |

## Project layout

```
app/
  main.py          app factory, security headers
  config.py        settings from environment
  security.py      passcode hashing, sessions, rate limiting
  deps.py          auth + role guards
  schemas.py       validated request models
  db/              repository interface, Firestore + in-memory implementations
  services/        assistant (decision engine), ai (Gemini), schedule/adherence, audit log, calendar links
  routers/         auth, members, medications, doses, appointments, activity
static/            web app: index.html, styles.css, app.js (router), js/ (api, dom, views)
tests/             pytest suite (in-memory DB, frozen clock, front-end safety checks)
```

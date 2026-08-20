# Health Journey Tracker

A private, mobile-friendly Streamlit app for a one-year health and dieting journey. It records
measurements, habits and fasting; converts one full-day food note into nutrition estimates with the
OpenAI API; manually syncs selected Garmin data; displays progress KPIs; and exports CSV/Excel backups.

> This application provides informational estimates only. It is not medical advice, and it is not a
> substitute for a clinician or registered dietitian. Seek professional care before making major
> diet or exercise changes, particularly if you have a medical condition.

## Architecture

- **Interface/backend:** Streamlit, entirely in Python and responsive in a phone browser.
- **Local database:** SQLite at `data/health_tracker.db`.
- **Hosted database:** Postgres through `DATABASE_URL` (Supabase, Neon, or another provider).
- **Food analysis:** OpenAI Responses API with Pydantic structured output. Only the food note is sent.
- **Garmin:** user-triggered sync through the unofficial `garminconnect` package.
- **Authentication:** a single password, stored only as a SHA-256 hash in server secrets.
- **Reminder:** a scheduled GitHub Actions email over SMTP, independent of Streamlit uptime.
- **Timezone:** Europe/London. Target date is interpreted as 1 September 2027.

SQLite is intentionally limited to local development. Streamlit Community Cloud does not provide a
durable local disk, so a deployed app must use hosted Postgres. This is the one material change from
the original proposal.

## Run locally with `uv`

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync
cp .env.example .env
uv run python scripts/make_password_hash.py
```

Paste the printed hash into `.env` as `APP_PASSWORD_HASH`. Add an OpenAI project API key as
`OPENAI_API_KEY`, then run:

```bash
uv run streamlit run app.py
```

Open <http://localhost:8501>. The `.env` file and local database are ignored by Git.

## Secrets

Local values go in `.env`. Streamlit Community Cloud values go in **App settings → Secrets** using
TOML syntax:

```toml
OPENAI_API_KEY = "..."
OPENAI_MODEL = "gpt-4.1-mini"
APP_PASSWORD_HASH = "..."
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
GARMIN_EMAIL = "..."
GARMIN_PASSWORD = "..."
```

Never commit API, database, email, or Garmin credentials. The OpenAI key remains on the Streamlit
server and is never sent to browser code.

## Deploy for phone access

1. Create a private GitHub repository and push this project.
2. Create a free Postgres project with Supabase or Neon and copy its connection string.
3. In Streamlit Community Cloud, create an app from the repository and set `app.py` as the entrypoint.
4. Add the secrets above. Do not deploy with the default SQLite URL.
5. Open the generated HTTPS address on the phone and add it to the home screen.

Check the current free-tier and private-repository availability of each hosting provider before
committing to it; service limits change. Database tables and default targets are created on first run.

## Daily email reminder

The workflow defaults to 19:00 UTC: 19:00 in UK winter and 20:00 in UK summer. GitHub cron is UTC,
so exact fixed UK clock time would require changing the cron when daylight saving changes.

For a no-extra-service option, use a Gmail account with 2-step verification and an app password. Add
these GitHub repository secrets:

| Secret | Example |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME` | sender Gmail address |
| `SMTP_PASSWORD` | Gmail app password |
| `REMINDER_FROM` | sender Gmail address |
| `REMINDER_TO` | destination email |
| `APP_URL` | deployed Streamlit URL |

Run **Actions → Daily health reminder → Run workflow** once to test it.

## Garmin limitations

Garmin sync imports steps, total calories, sleep duration, resting heart rate, and an activity summary.
The integration uses an unofficial API and can stop working if Garmin changes authentication or data
formats. It is therefore manual and isolated from the rest of the app; all imported fields remain
visible in the check-in before saving.

## Data and backups

The Targets & export page downloads a complete flattened CSV or Excel workbook. Download a backup
regularly. Hosted Postgres providers usually also offer database backups, subject to their plan.

## Developer checks

```bash
uv run ruff check .
uv run pytest
```


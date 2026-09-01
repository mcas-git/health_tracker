# Health Journey Tracker

A private, mobile-friendly Streamlit app for a one-year health and dieting journey. It records
measurements, habits and fasting; converts one full-day food note into nutrition estimates with the
OpenAI API; distinguishes complete from partial journals; manually syncs selected Garmin data;
displays monthly checkpoints and progress KPIs; offers reviewed weekly calorie adjustments; and
exports CSV, Excel, and encrypted full backups.

> This application provides informational estimates only. It is not medical advice, and it is not a
> substitute for a clinician or registered dietitian. Seek professional care before making major
> diet or exercise changes, particularly if you have a medical condition.

## Architecture

- **Interface/backend:** Streamlit, entirely in Python and responsive in a phone browser.
- **Local database:** SQLite at `data/health_tracker.db`.
- **Hosted database:** Postgres through `DATABASE_URL` (Supabase, Neon, or another provider).
- **Food analysis:** OpenAI Responses API with Pydantic structured output. Only the food note is sent.
- **Garmin:** user-triggered sync through the unofficial `garminconnect` package.
- **Authentication:** Google OpenID Connect in production, restricted to an email allowlist and
  protected by the Google account's 2-Step Verification. A hashed password remains available only
  as a local-development fallback when Google authentication is not configured.
- **Reminders and report:** scheduled GitHub Actions emails over SMTP, independent of Streamlit
  uptime.
- **Backups:** encrypted full-database downloads, safe merge-restore, and an optional monthly
  encrypted email attachment.
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
BACKUP_ENCRYPTION_KEY = "..."
ALLOWED_EMAIL = "your-google-email@gmail.com"

[auth]
redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
cookie_secret = "..."
client_id = "...apps.googleusercontent.com"
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Keep all root-level secrets above the `[auth]` section. Never commit the Google client secret or
cookie secret. When `[auth]` is present, the deployed app uses Google sign-in and accepts only the
address in `ALLOWED_EMAIL`. `APP_PASSWORD_HASH` is used only when Google authentication is absent,
such as local development.

Never commit API, database, email, or Garmin credentials. The OpenAI key remains on the Streamlit
server and is never sent to browser code.

Generate the backup encryption key once with:

```bash
uv run python scripts/make_backup_key.py
```

Store the printed value in local `.env`, Streamlit secrets, GitHub Actions secrets, and a separate
password manager. Existing encrypted backups cannot be restored if this key is lost or replaced.

## Deploy for phone access

1. Create a private GitHub repository and push this project.
2. Create a free Postgres project with Supabase or Neon and copy its connection string.
3. In Streamlit Community Cloud, create an app from the repository and set `app.py` as the entrypoint.
4. Add the secrets above. Do not deploy with the default SQLite URL.
5. Open the generated HTTPS address on the phone and add it to the home screen.

Check the current free-tier and private-repository availability of each hosting provider before
committing to it; service limits change. Database tables and default targets are created on first run.

### Change the local-development password

Generate a replacement hash locally with `uv run python scripts/make_password_hash.py`. In Streamlit
Community Cloud, open the app's **Settings → Secrets**, replace only `APP_PASSWORD_HASH`, and save.
After Streamlit restarts locally, sign in with the new plain-text password. Never paste the plain
password or its hash into GitHub files. Production Google authentication is managed through the
Google Auth Platform and Streamlit secrets instead.

## Email reminders and weekly report

Daily reminders run at 05:00 and 21:00 Europe/London. The evening email is skipped only when that
day's evening check-in is complete. A weekly coaching report is sent each Sunday at 19:00
Europe/London. The workflows run at both possible UTC offsets and the Python scripts suppress the
duplicate, so the times remain stable across GMT and BST.

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
| `DATABASE_URL` | the same hosted Postgres URL used by Streamlit |
| `BACKUP_ENCRYPTION_KEY` | the key printed by `scripts/make_backup_key.py` |

Run **Actions → Daily health reminder → Run workflow**, **Actions → Weekly health report → Run
workflow**, and **Actions → Monthly encrypted backup → Run workflow** once to test them. The monthly
backup is sent on the first day of each month at 19:00 Europe/London and is skipped harmlessly until
`BACKUP_ENCRYPTION_KEY` is configured. For GitHub Actions, use a Supabase connection URL that is
reachable over IPv4 (normally the session pooler URL) if the direct database hostname is IPv6-only.

## Garmin limitations

Garmin sync imports steps, total calories, sleep duration, resting heart rate, and an activity summary.
The integration uses an unofficial API and can stop working if Garmin changes authentication or data
formats. It is therefore manual and isolated from the rest of the app; all imported fields remain
visible in the check-in before saving.

## Data and backups

The Targets, backup and privacy page downloads flattened CSV/Excel data and a complete encrypted
backup. Encrypted restores are validated and merged transactionally: matching dates and settings are
replaced while unrelated records are retained. Hosted Postgres providers may also offer database
backups, subject to their plan.

## Developer checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The same checks run automatically in GitHub Actions for every push and pull request.

<div align="center">
  <img src="docs/assets/nu-logo.svg" width="230">

<h1>Install and run</h1>

<p>From a clean checkout to a local site</p>
</div>

[README](README.md) · [INSTALL](INSTALL.md) · [User guide](docs/USER_GUIDE.md) ·
[Architecture](docs/ARCHITECTURE.md) · [Database](docs/DATABASE.md) ·
[Security](docs/SECURITY.md) · [Reviewer guide](docs/REVIEWER_GUIDE.md) ·
[Design](docs/DESIGN.md)

> [!NOTE]
> This file covers local setup, database configuration and startup.
> It does not cover product tasks or architecture (see [User guide](docs/USER_GUIDE.md)
> and [Architecture](docs/ARCHITECTURE.md)).

## Prerequisites

- Windows PowerShell and Python available as `python` on `PATH`.
- MySQL Server 8.4.7 and a database account with permission to create and
  migrate the app schema. Database character set: `utf8mb4`.
- Network access to install packages from `requirements.txt` on first setup.
- SMTP credentials for real email delivery. Development can print verification
  codes to the server log when SMTP is unavailable.

The dependency file declares Flask `>=3.0,<4.0`, SQLAlchemy through
Flask-SQLAlchemy `>=3.1,<4.0`, Flask-Migrate `>=4.0,<5.0`, and PyMySQL
`>=1.1,<2.0`. This installation uses MySQL Server 8.4.7. No virtual environment
is assumed to exist. The `first_time_startup.ps1` startup script creates `.venv/` when
it is missing.

## First-time setup wizard

Run `first_time_startup.ps1` from the project root. This all-in-one wizard creates
.venv if needed, installs requirements, and copies .env.example to .env only if
.env does not already exist. If it creates .env, open Notepad so you can
set the database URL, secret key and email settings. It then gives you the SQL
to create the dentalconnect database in phpMyAdmin and runs the migrations.

The wizard next offers to create the first administrator. If you accept, it
collects the administrator details, generates SQL containing the password hash,
and copies that SQL to the clipboard for you to run in phpMyAdmin. The wizard
then lets you start either the debug server or the Waitress server, or exit.
This covers setup through first startup, no separate administrator command is
needed when you create the account in the wizard.

## Database and environment

Create a database and a least-privilege MySQL user, substituting local values:

```sql
CREATE DATABASE dentalconnect CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'dentalconnect_user'@'localhost' IDENTIFIED BY '<local-password>';
GRANT ALL PRIVILEGES ON dentalconnect.* TO 'dentalconnect_user'@'localhost';
FLUSH PRIVILEGES;
```

In PowerShell, copy `.env.example` to `.env`, then set values appropriate to
your machine:

```powershell
Copy-Item .env.example .env
```

The `.env.example` URL is:

```text
mysql+pymysql://dentalconnect_user:strong-password@localhost/dentalconnect?charset=utf8mb4
```

Replace the example username and password. Never commit `.env`.

| Variable | Purpose | Example placeholder | Production configuration checks |
| --- | --- | --- | --- |
| `APP_ENV` | Selects development or production checks. | `development` | Optional. Set `production` to enable strict production checks. |
| `SECRET_KEY` | Signs sessions, reset links and OTP digests. | `<long-random-secret>` | Yes. At least 32 characters. |
| `DATABASE_URL` | SQLAlchemy database connection. | `mysql+pymysql://<user>:<password>@<host>/<db>?charset=utf8mb4` | Yes. MySQL driver URL. |
| `COOKIE_SECURE` | Marks session/device cookies Secure. | `false` locally, `true` in production. | Yes. Must be `true`. |
| `APP_BASE_URL` | Base URL used in email links. | `http://127.0.0.1:5000` | Yes. Must start with `https://`. |
| `MAIL_SERVER` | SMTP host. | `smtp.example.com` | Yes. |
| `MAIL_PORT` | SMTP port. | `587` | Yes. |
| `MAIL_USE_TLS` | SMTP STARTTLS setting. | `true` | TLS or SSL required. Not both. |
| `MAIL_USE_SSL` | SMTP SSL setting. | `false` | TLS or SSL required. Not both. |
| `MAIL_USERNAME` | SMTP login. | `<smtp-user>` | Yes. |
| `MAIL_PASSWORD` | SMTP credential. | `<smtp-password>` | Yes. |
| `MAIL_DEFAULT_SENDER` | From header for outgoing mail. | `NU DentalConnect <noreply@example.com>` | Yes. |

`MAIL_PORT` defaults to `587`, `MAIL_USE_TLS` to `true`, `MAIL_USE_SSL` to
`false`, and `APP_BASE_URL` to `http://127.0.0.1:5000` in `config.py`.
The `.env.example` leaves SMTP username and password blank.

### Create the first administrator

The normal first-run path is to accept the administrator-creation prompt in
`first_time_startup.ps1`. It asks for the administrator's name, email, phone and
password (at least 8 characters, confirmed twice), then generates SQL with a
Werkzeug password hash. Run the copied SQL
in phpMyAdmin against the dentalconnect database and return to the wizard to
continue.

If you skip administrator creation in the wizard, or are following the manual
setup alternative, you can create one later with `flask create-admin`.

### Manual setup alternative

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:FLASK_APP = "run.py"
flask db upgrade
flask create-admin
```

For a shell where Bash is available, the equivalent environment and CLI steps
are:

<details>
<summary>Bash manual setup</summary>

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export FLASK_APP=run.py
flask db upgrade
flask create-admin
```
</details>

## Start the site

After the first-time wizard finishes, use one of these scripts for later
starts. Both expect the wizard (or the manual setup steps) to have created
.venv and installed the requirements. They do not create the environment,
install packages, or run migrations.

- `start_debug.ps1` sets `FLASK_APP=run.py` and starts Flask's debug server.
- `start_production.ps1` sets `FLASK_APP=run.py` and starts the app with Waitress.

Both scripts use the APP_ENV value from .env. APP_ENV defaults to development,
so running Waitress alone does not enable the strict production configuration
checks. Set APP_ENV=production when you want those checks enforced. Production
settings then require HTTPS, secure cookies, MySQL and complete SMTP settings.

## You are done when…

- [ ] The first-time wizard completes migrations against the intended MySQL database.
- [ ] If you chose to create an administrator, its generated SQL runs successfully in phpMyAdmin.
- [ ] `start_debug.ps1` prints the Flask development-server address, or
      `start_production.ps1` reports Waitress listening.
- [ ] The home page opens at `http://127.0.0.1:5000`.
- [ ] A new account reaches the email verification form. In development without
      SMTP, the server log contains a `[DEV OTP]` line.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Can't connect` / access denied during migration | MySQL service, user grant or `DATABASE_URL` is wrong. | Start MySQL, check the DB name, user, password and grant. |
| `missing recruitment_listings.submission_key` | Existing schema is behind the model/migration state. | Back up first. Check `flask db current` and `flask db upgrade` against the same configured database. |
| OTP email never arrives | SMTP is unset, blocked, or rejected. Development may log the code instead. | Check server output and SMTP host, port, TLS/SSL, username and password. In development, read `[DEV OTP]`. In production, configure SMTP. |
| Startup says `SECRET_KEY` is missing | Production mode is active without a key. | Set `SECRET_KEY` to a long random value (32+ characters) in `.env`. |
| Production startup rejects the URL or cookie | Production checks require MySQL, HTTPS and `COOKIE_SECURE=true`. | Set a MySQL `DATABASE_URL`, HTTPS `APP_BASE_URL` and secure cookies. |

---

[README](README.md) · [INSTALL](INSTALL.md) · [User guide](docs/USER_GUIDE.md) ·
[Architecture](docs/ARCHITECTURE.md) · [Database](docs/DATABASE.md) ·
[Security](docs/SECURITY.md) · [Reviewer guide](docs/REVIEWER_GUIDE.md) ·
[Design](docs/DESIGN.md)
<div align="center">
  <img src="assets/nu-logo.svg" width="220">

<h1>Reviewer guide</h1>

<p>A presentation path that follows the running application</p>
</div>

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](SECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)

> [!NOTE]
> This file covers a concise presentation, demo sequence and reviewer questions.
> It does not replace the usage instructions or installation guide (see
> [User guide](USER_GUIDE.md) and [INSTALL](../INSTALL.md)).

Documentation viewing context: [INSERT WHERE THE REVIEWER VIEWS DOCS: GitHub web / VS Code preview / PDF] (assume GitHub web; Markdown uses GitHub-compatible features).

## 60-second pitch

NU DentalConnect is a server-rendered Flask application for dentistry students
to publish procedure listings and patients to find and request appointments.
Patients can also submit a separate application expressing interest. Students
review applications and appointment requests in their workspace; a requested
time stays pending until the student confirms it or proposes another time.
Student accounts must verify email and receive administrator approval before
they can sign in. Administrators review that queue and manage accounts,
listings, appointments and audit history. The database stores identity,
profile and scheduling information; there is no diagnosis or medical-record
model.

## 10-minute demo

Prepare an available student registration email and administrator account
through the approved demo-account process. The three role accounts are defined
in `reset_seed_accounts.sql`; ask the project owner for access through the
approved channel. A student flow needs a deliverable OTP; development fallback
codes appear in the server log. Do not display or read aloud seed credentials.

| Time | Exact path and action |
| --- | --- |
| 0:00–0:45 | Open `/` (Home). Point out search and the distinction between a request and an application. |
| 0:45–1:30 | Open **Find an appointment** → search a published listing → open its detail. |
| 1:30–2:15 | Open **Create account** → register a student → enter the OTP from email or development log. Show **Account pending approval**. |
| 2:15–3:15 | Sign in as admin → **Pending students** → select **Approve**. |
| 3:15–4:00 | Sign in as the approved student → **Post an appointment listing** → use a built-in or saved template → publish. |
| 4:00–5:00 | Sign in as patient → **Find an appointment** → open the new listing → submit an application and request a future time. |
| 5:00–6:00 | Sign in as student → **Applications** → open the listing → accept/reject an application; return to **Dashboard** and confirm or propose another time. |
| 6:00–7:00 | Sign in as patient → **Dashboard** → show application/appointment statuses; accept a proposed time if used. |
| 7:00–8:00 | As patient, open the student's profile from the listing; as student, open a patient profile only after a qualifying contact. |
| 8:00–9:00 | As admin, open **Accounts** → set a non-admin password, then **Audit history** → filter an event. |
| 9:00–10:00 | Close with the conflict check, the approval gate, and the known limits below. |

Use separate browser profiles or sign out between roles. The exact visible menu
labels are in `app/templates/base.html`; the action controls are in the linked
role templates.

## Code-backed capability crosswalk

The repository does not contain the instructor's official 13 required-feature
labels. These 13 rows map observable implementation areas to source and a demo
step; they are not represented as the official rubric wording.

| # | Verified capability | Main code | Demo |
| --- | --- | --- | --- |
| 1 | Patient/student role registration | `app/forms.py`, `app/routes/auth.py` | 1–2 |
| 2 | Email OTP verification and resend | `app/services.py`, `app/routes/auth.py` | 2 |
| 3 | Student approval gate | `app/approval.py`, `app/routes/admin.py` | 2–3 |
| 4 | Password login, logout and reset | `app/models.py`, `app/routes/auth.py` | 3–9 |
| 5 | Patient/student profile editing and avatars | `app/routes/main.py`, `app/upload.py` | 7–8 |
| 6 | Search and browse published listings | `app/routes/main.py`, `app/templates/recruitment/` | 1–2 |
| 7 | Student listing create/edit/status | `app/routes/student.py`, `app/templates/student/listing_form.html` | 3–4 |
| 8 | Built-in and saved listing templates | `app/listing_presets.py`, `app/routes/student.py` | 3–4 |
| 9 | Patient applications and student decisions | `app/routes/patient.py`, `app/routes/student.py` | 5–6 |
| 10 | Appointment requests and student confirmation | `app/routes/patient.py`, `app/routes/student.py` | 5–6 |
| 11 | Reschedule proposals and one-hour conflict check | `app/services.py`, role routes | 5–6, 9 |
| 12 | In-app notifications and email templates | `app/models.py`, `app/services.py`, `app/templates/emails/` | 3, 5–7 |
| 13 | Admin accounts, oversight and audit history | `app/routes/admin.py`, `app/audit.py` | 3, 8–9 |

## What to look for

- A newly verified student remains pending until an administrator approves.
- Applications and appointment requests appear as different records and actions.
- A student confirmation is required before a requested time becomes confirmed.
- An overlapping confirmed student slot cannot be confirmed.
- A student sees patient contact fields only after an active application or
  appointment relationship; denied profile attempts are audited.
- The admin password form never targets admin accounts and invalidates sessions.

## Likely reviewer questions

### Which responsive framework is used?

`base.html` always loads `app/static/css/app.css` and conditionally loads the
bundled Bootstrap 5.2.3 stylesheet from
`app/static/bootstrap/css/bootstrap.min.css` on student application, student
appointment, student dashboard and profile endpoints. Bootstrap is not loaded
on every route; custom `app.css` defines the overall interface.

### How are accounts protected?

Passwords use Werkzeug's hash and check functions; forms use Flask-WTF CSRF.
Login and session loading require active, verified accounts and approved
students. See `app/models.py`, `app/forms.py` and `app/routes/auth.py`.

### How does student approval work?

Registration creates students as pending; email verification adds them to the
admin queue but does not unlock sign-in. An administrator approves or rejects
the request in `app/routes/admin.py` using `StudentApprovalService`.

### What is the difference between an application and an appointment?

An application is a message of interest attached to a listing. An appointment
request asks for a date and time and remains pending until a student confirms
or proposes a different time; the records and routes are separate.

### What happens when a time conflicts?

`services.py` checks nearby confirmed appointments for the student before
confirmation. The conflict query is also covered by the route workflow test in
`tests/test_workflows.py`.

### What data does the project store?

The models store account identity, student/patient profile fields, listings,
applications, appointment schedules, notifications, OTP digests and audit
events. There is no diagnosis or medical-record model; see `app/models.py`.

### Which database was tested?

The included test fixtures use isolated in-memory SQLite, and the production
configuration requires a MySQL SQLAlchemy URL. This test run does not establish
that migrations or behavior were verified against a live MySQL server.

### Is OTP delivery verified?

Tests replace email sending with a test double. Real SMTP delivery was not
verified in this audit; development can log OTP codes when SMTP is absent.

### Are there rate limits?

OTP issue and verification flows enforce delays, hourly limits and attempt
limits in `app/services.py`. The login route has no active attempt throttle;
`login_lockout` is only an audit method.

### What does the audit log capture?

It stores actor and entity snapshots, action-specific details, IP address,
user-agent, and device labels plus a truncated device-ID hash. It does not
claim to be an immutable or tamper-proof log; see `app/audit.py` and
`app/models.py`.

### Is Bootstrap the whole interface?

No. `base.html` always loads `app.css` and conditionally loads Bootstrap 5.2.3
on a selected student and profile route set; the custom file owns the visual
tokens and extensive responsive layout rules. The app is rendered with Jinja.

### What remains unverified?

Live MySQL setup/migrations, real SMTP delivery, GitHub's renderer, and the
reviewer's exact environment were not exercised. The migration chain in
`DATABASE.md` was read from revision files, not queried from a database.

### What is not built?

The code does not contain login rate limiting, a CSP header, malware scanning,
payment processing, or a diagnosis/medical-record workflow. The patient
application-message lookup is also not scoped to the student's listing; see
the privacy limitation in `SECURITY.md`. These should not be presented as
implemented features.

### Where are demo passwords?

This guide intentionally does not reproduce seed data. The SQL file contains
credential material and resets the `dentalconnect` dataset; the account owner
must provide access through an approved channel. See [INSTALL](../INSTALL.md).

---

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](SECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)
<div align="center">
  <img src="assets/nu-logo.svg" width="220">

<h1>Security model</h1>

<p>Controls implemented in the current source</p>
</div>

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](SECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)

> [!NOTE]
> This file covers implemented security controls, access rules and known limits.
> It does not claim compliance or describe setup (see [INSTALL](../INSTALL.md)
> and [Architecture](ARCHITECTURE.md)).

## Account and session controls

- `User.set_password()` and `check_password()` delegate to Werkzeug password
  hashing and verification; plaintext passwords are not stored by the model.
- Registration and password forms require at least 12 characters, upper and
  lowercase letters, and a digit. Passwords are bounded to 128 characters.
- Flask-WTF global CSRF protection covers form posts. Production enables strict
  HTTPS referrer checks for CSRF.
- Session cookies are HttpOnly and SameSite=Lax. Production config requires
  `COOKIE_SECURE=true`, a 32-character-or-longer secret and HTTPS `APP_BASE_URL`.
  The application sets HSTS when secure cookies are enabled.
- Permanent login sessions have an eight-hour lifetime; CSRF tokens expire
  after one hour.
- The login manager stores `user_id:auth_version`. Password resets, password
  changes, admin password setting and deactivation increment the version; the
  user loader rejects stale sessions.
- Password-reset tokens are signed with the application secret and expire after
  30 minutes. Reset responses do not disclose whether an account exists.

## Email verification and throttling

Email verification uses six-digit OTPs. `services.py` stores an HMAC-SHA256
digest keyed by `SECRET_KEY`, expires codes after 10 minutes, allows up to five
attempts per challenge and five attempts per user per hour, and enforces a
60-second delay and five-issued-codes-per-hour limit. Comparison uses
`hmac.compare_digest`; successful codes are consumed. Development logs the code
when SMTP is unavailable. Production configuration requires SMTP.

There is no login-attempt throttle in the current login route. `login_lockout`
is an audit action method, not evidence of an active lockout control.

## Authorization matrix

| Resource or action | Patient | Student | Administrator |
| --- | --- | --- | --- |
| Patient dashboard and own applications/appointments | Own records | — | Aggregate overview |
| Create/edit listing or listing template | — | Own records, after approval | Oversight and close/delete |
| Student profile | Active, verified, approved students | Denied | Any profile |
| Patient profile | Other patients hidden | Only after active application or appointment with that student | Any profile |
| Approval queue and account administration | Denied | Denied | Allowed |
| Audit history | Denied | Denied | Allowed |

Anonymous visitors can browse approved published listings but cannot view
profiles. Profile routes require sign-in. `ProfileAccessPolicy` returns
not-found for patient profiles without a qualifying relationship, while
student-to-student access is forbidden. Contact is active when an application
is pending/accepted or an appointment is pending/confirmed/reschedule-requested/
completed. A withdrawn/rejected application or cancelled/rejected appointment
alone does not grant access. Admins can view all role profiles; only admins can
view another administrator profile.

Both login and user loading require active accounts, verified email and
approved student status. Admin password setting refuses administrator targets,
increments `auth_version` and notifies the target without putting the password
in the message.

## Upload controls

`upload.py` decodes image content instead of trusting request MIME headers,
accepts only JPEG/PNG/WebP, caps profile images at 2 MiB and listing covers at
4 MiB, limits decoded images to 50 megapixels, and resizes to 512px or 1600px.
Images are re-encoded under random UUID filenames outside the static directory.
The overall request size limit is 5 MiB. Serving routes apply ownership and
profile/listing visibility checks.

## Response headers and audit data

Every response sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`, and a restrictive
`Permissions-Policy`. HSTS is added when secure-cookie mode is active. No
Content-Security-Policy header is configured in `app/__init__.py`.

`AuditLog` rows contain actor ID when available, actor email snapshot, action,
entity type/ID, event-specific JSON details, request IP, user-agent and UTC
creation time. `DeviceInfo` adds parsed browser/OS/device type and a truncated
SHA-256 hash of the opaque device cookie; it does not store the cookie value.
Events cover login/register/OTP/password, profile access and edits, listing,
template, application, appointment, notification and administrator actions.
The event vocabulary is defined in `AuditLogger.ACTION_*` in `app/audit.py`.
Audit history is not shown as tamper-proof or immutable by this application.

## Known limitations

- The code does not establish legal or regulatory compliance. No such claim is
  made here.
- Login attempts are audited but not rate-limited or locked out by the route.
- There is no configured Content-Security-Policy header.
- The patient-profile access decision is scoped to the viewing student, but the
  displayed `application_message` lookup is scoped only to the patient and
  active application status. It may therefore select a message from another
  student's listing; see `ProfileAccessPolicy.get_visible_patient_fields()`.
- Uploads are validated and re-encoded but have no malware-scanning step.
- Runtime uploads and the database are local deployment responsibilities; this
  repository does not configure backups, monitoring or a public TLS proxy.
- MySQL migrations and production SMTP delivery were not exercised by the
  isolated SQLite test suite.

---

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](SECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)
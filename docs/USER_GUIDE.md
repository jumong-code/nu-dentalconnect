<div align="center">
  <img src="assets/nu-logo.svg" width="220">

<h1>User guide</h1>

<p>Task walkthroughs for each account role</p>
</div>

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](CYBERSECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)

> [!NOTE]
> This file covers actions available in the patient, student and administrator screens.
> It does not cover installation or internal design (see [INSTALL](../INSTALL.md)
> and [Architecture](ARCHITECTURE.md)).

## <img src="assets/patient.svg" alt="Patient role icon" width="36"> Patient

### Create an account and verify email

1. Open **Create account** from the sign-in page.
2. Choose **Patient**, fill the required name, email, phone and password fields,
   then select **Create account**.
3. Enter the six-digit code on **Verify your email**. If needed, use **Resend
   code**; the screen explains the wait and hourly limits.
4. Return to **Sign in**. Patients do not wait for administrator approval.

If development SMTP is not configured, use the code printed in the server log.
That fallback is for development only; production requires SMTP configuration.

### Find a listing and contact a student

1. Choose **Find appointments** in the navigation.
2. Search by keyword, category or schedule, then open a listing.
3. From the listing detail page, choose **Request appointment** to ask for a
   date and time. The request remains pending until the student responds.
4. Alternatively, submit **Send patient application** with an optional message.
   This expresses interest and is not an appointment request.

### Manage requests

Open **My appointments**. In **Appointments**, use **Accept proposed time**, **Send**
for a reschedule request, or **Cancel appointment** as available for that
request's state. In **Patient applications**, use **Withdraw application** while
an application is pending. New activity also appears in notifications.

### Edit profile and view a student

Open **My account** to change your name, email or phone, update your avatar, or
change your password. Changing your email signs you out and requires a new OTP.
Open a student name from a listing or dashboard to view their approved profile
and published listings.

## <img src="assets/student.svg" alt="Dentistry student role icon" width="36"> Dentistry student

### Verify and wait for approval

1. Register as **Dentistry student** and submit the six-digit email code.
2. After verification, the site shows **Account pending approval**. You cannot
   sign in or publish listings during this wait.
3. An administrator reviews the request under **Pending Students**. After
   approval, return to **Sign in**. Approval sends an in-app notice and attempts
   email notification.

### Create and publish listings

From the student **Dashboard**, choose **Post an appointment**. Fill
the procedure fields and choose whether to publish immediately or save a draft.
On the listing form, **Save these fields as a template** stores the entered
fields separately; it does not save the listing. Use **Saved templates**
to start from built-in or saved templates. The template directory lets you
delete saved templates you own.

From the dashboard, listing actions include **Publish**, **Close**, **Reopen as
draft**, **Edit**, and **Delete** where allowed. A closed listing can be reopened
as a draft, but not republished directly; create or reopen as a draft first.

### Review applications and appointment requests

- Open **Patient applications** for all listings, or **View applications** on one
  listing. A pending application can be accepted or rejected.
- Open **Appointments** or the dashboard's **Requests to answer**. Confirm or
  reject a pending request, or propose another time. A student may also mark a
  past confirmed appointment complete or cancel an upcoming one.
- Click a patient name after an active application or appointment to view the
  contact fields allowed by the profile policy. Withdrawing/cancelling all
  qualifying contact removes that access.

## <img src="assets/admin.svg" alt="Administrator role icon" width="36"> Administrator

### Approve a student

1. Sign in with an administrator account created by `flask create-admin` or
   provisioned for the demo.
2. From **Platform overview**, select **Pending students**.
3. Inspect the verified student in the queue, then choose **Approve** or
   **Reject**. Rejection deactivates the account; it does not delete it.

Only email-verified active students appear in the queue. The student must be
approved before signing in.

### Set a non-admin user's password

Open **Accounts**, find a patient or student, and select **Set password**. Enter
and confirm the new password. This action changes the password, invalidates
existing sessions, records an audit event and attempts to notify the account by
email. Administrators cannot use this screen to set another administrator's
password.

### Review profiles, listings and audit history

- **Accounts** supports name/email search and role filtering. Account actions
  include activate/deactivate and permanent deletion with typed-email
  confirmation. The last active administrator cannot be deleted.
- **Appointment listings** provides close and delete actions. Deleting a
  listing with future confirmed appointments requires an explicit confirmation.
- **Appointments** provides administrative deletion.
- **Audit history** can be filtered by action, actor and date range. Results
  display newest first; rows are paginated.
- Open a profile from **Accounts** to view its basic information. Administrators
  can view all profile roles.

---

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](CYBERSECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)
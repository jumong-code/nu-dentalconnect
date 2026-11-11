from datetime import timedelta
from urllib.parse import urlparse
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user, login_required
from ..approval import StudentApprovalService
from ..audit import audit_logger, get_device_info
from ..extensions import db
from ..forms import LoginForm, RegisterForm, ResetRequestForm, ResetPasswordForm, ResendOTPForm, VerifyOTPForm, ResumeVerificationForm
from ..models import DentistryStudent, Patient, User
from ..services import issue_email_otp, send_email, verify_email_otp

bp = Blueprint("auth", __name__)

SPAM_HINT = "If it does not arrive, check your spam or junk folder."


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        # An unverified account can resume verification instead of creating a
        # second row for the same address.
        existing_user = User.query.filter_by(email=email, is_active=True, email_verified=False).first()
        if existing_user:
            sent = issue_email_otp(existing_user)
            db.session.commit()
            flash(
                ("Enter the verification code sent to your email. " + SPAM_HINT) if sent
                else "No new email was sent. Wait 60 seconds before retrying; if it still does not arrive, outgoing email may be unavailable. " + SPAM_HINT,
                "info",
            )
            return redirect(url_for("auth.verify_email", email=existing_user.email))

        user = User(
            full_name=form.full_name.data,
            email=email,
            role=form.role.data,
            phone=form.phone.data or None,
            email_verified=False,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        if user.role == "patient":
            db.session.add(Patient(user=user))
        else:
            db.session.add(DentistryStudent(
                user=user,
                year_level=form.year_level.data or None,
                campus=form.campus.data or None,
            ))
            # New students are locked until an administrator approves them.
            StudentApprovalService.mark_pending(user)
        db.session.commit()
        device = get_device_info(request)
        audit_logger.account_registered(user=user, role=user.role, device=device, success=True)
        sent = issue_email_otp(user)
        db.session.commit()
        flash(
            ("Enter the verification code sent to your email. " + SPAM_HINT) if sent
            else ("Your account was created, but email delivery is unavailable. In development, check the server log for the code; otherwise ask the site administrator to configure email delivery. " + SPAM_HINT),
            "info",
        )
        return redirect(url_for("auth.verify_email", email=user.email))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        device = get_device_info(request)
        # Every account-state message is emitted only after the password matches,
        # so an anonymous visitor cannot enumerate registered addresses.
        if user and user.is_active and user.check_password(form.password.data):
            if not user.email_verified:
                sent = issue_email_otp(user)
                db.session.commit()
                audit_logger.login_failure(email=email, device=device, reason="email_not_verified")
                flash(
                    ("Enter the verification code sent to your email. " + SPAM_HINT) if sent
                    else "Email delivery is temporarily unavailable. Use Resend code when email service is restored.",
                    "info",
                )
                return redirect(url_for("auth.verify_email", email=user.email))
            if not user.is_approved():
                audit_logger.login_failure(email=email, device=device, reason="pending_admin_approval")
                db.session.commit()
                flash("Your email is verified. An administrator must approve your student account before you can sign in.", "info")
                return redirect(url_for("auth.await_approval", email=user.email))
            audit_logger.login_success(user=user, device=device, remember=True)
            db.session.commit()
            login_user(user, remember=True, duration=timedelta(hours=8), fresh=True)
            session.permanent = True
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url and urlparse(next_url).netloc == "":
                return redirect(next_url)
            return redirect(url_for("main.dashboard"))
        audit_logger.login_failure(email=email, device=device, reason="invalid_credentials")
        flash("We could not sign you in. Check your details and verify your email if you have not already.", "error")
    return render_template("auth/login.html", form=form)


@bp.route("/await-approval")
def await_approval():
    """Page shown to students whose email is verified but not yet approved."""
    email = request.args.get("email", "").strip().lower()
    if not email:
        return redirect(url_for("auth.login"))
    user = db.session.scalar(db.select(User).where(
        User.email == email,
        User.role == "student",
        User.approval_status == StudentApprovalService.PENDING,
        User.is_active.is_(True),
    ))
    return render_template("auth/await_approval.html", email=email, user=user)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    device = get_device_info(request)
    audit_logger.logout(user=current_user, device=device)
    db.session.commit()
    logout_user()
    flash("You have signed out.", "success")
    return redirect(url_for("main.index"))


@bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    form = VerifyOTPForm()
    if request.method == "GET" and request.args.get("email"):
        form.email.data = request.args.get("email", "")[:255]
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(db.select(User).where(User.email == email, User.is_active.is_(True)))
        device = get_device_info(request)
        verified = bool(user and not user.email_verified and verify_email_otp(user, form.code.data))
        db.session.commit()
        if verified:
            audit_logger.email_verified(user=user, device=device)
            if user.role == "student":
                StudentApprovalService.email_verified(user)
            db.session.commit()
            if user.role == "student" and not user.is_approved():
                flash("Email verified. Your student account is now awaiting administrator approval.", "info")
                return redirect(url_for("auth.await_approval", email=user.email))
            flash("Email verified. You can sign in now.", "success")
            return redirect(url_for("auth.login"))
        audit_logger.otp_failed(email=email, device=device, reason="invalid_or_expired")
        flash("The code is invalid, expired, or already used. Request a new code and try again.", "error")
    resend_form = ResendOTPForm()
    resend_form.email.data = form.email.data
    return render_template("auth/verify_email.html", form=form, resend_form=resend_form)


@bp.route("/resume-verification", methods=["GET", "POST"])
def resume_verification():
    """Standalone page to resume verification for an unverified account."""
    form = ResumeVerificationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(db.select(User).where(
            User.email == email,
            User.is_active.is_(True),
            User.email_verified.is_(False),
        ))
        device = get_device_info(request)
        if user:
            sent = issue_email_otp(user)
            db.session.commit()
            if sent:
                audit_logger.otp_resent(user=user, device=device)
            db.session.commit()
        else:
            sent = False
        # Generic response: never reveal whether an account exists.
        flash("If an unverified account matches that address, a new code was sent when allowed. Codes expire after 10 minutes; allow 60 seconds between requests, with up to 5 codes per hour. If no email arrives, outgoing email may be unavailable. " + SPAM_HINT, "info")
        return redirect(url_for("auth.verify_email", email=email))
    return render_template("auth/resume_verification.html", form=form)


@bp.route("/resend-verification", methods=["POST"])
def resend_verification():
    form = ResendOTPForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(db.select(User).where(
            User.email == email,
            User.is_active.is_(True),
            User.email_verified.is_(False),
        ))
        device = get_device_info(request)
        if user:
            sent = issue_email_otp(user)
            db.session.commit()
            if sent:
                audit_logger.otp_resent(user=user, device=device)
            db.session.commit()
        else:
            sent = False
    else:
        user = None
        sent = False
    flash("If the account can receive a code, a new verification email was sent when allowed. Codes expire after 10 minutes; allow 60 seconds between requests, with up to 5 codes per hour. If no email arrives, outgoing email may be unavailable. " + SPAM_HINT, "info")
    return redirect(url_for("auth.verify_email", email=form.email.data.strip().lower() if form.email.data else ""))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    form = ResetRequestForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email, is_active=True).first()
        device = get_device_info(request)
        if user:
            token = user.get_reset_token()
            send_email(
                user.email,
                "Reset your NU DentalConnect password",
                "reset",
                user=user,
                token=token,
                base_url=current_app.config["APP_BASE_URL"].rstrip("/"),
            )
            audit_logger.password_reset_requested(user=user, device=device)
        else:
            audit_logger.password_reset_requested(email=email, device=device, user_not_found=True)
        db.session.commit()
        flash("If an active account matches that email, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.verify_reset_token(token)
    if not user or not user.is_active:
        flash("That reset link is invalid or expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        device = get_device_info(request)
        user.set_password(form.password.data)
        user.auth_version += 1
        audit_logger.password_reset(user=user, device=device)
        db.session.commit()
        flash("Your password has been updated.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", form=form)

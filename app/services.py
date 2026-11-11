import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from html import unescape
from flask import current_app, has_request_context, render_template, request
from flask_mail import Message
from jinja2 import TemplateNotFound
from .extensions import db, mail
from .models import Appointment, AuditLog, DentistryStudent, Notification, OTPVerification, User, utcnow
from .time_utils import MANILA_TZ


def send_email(to, subject, template, **context):
    if not current_app.config.get("MAIL_SERVER") or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info("Email not sent: SMTP is not configured (recipient omitted).")
        return False
    try:
        # Templates use {{ now.year }} in the footer. Supplying "now" here keeps
        # every email renderable even when a caller forgets to pass it.
        context.setdefault("now", datetime.now(timezone.utc).astimezone(MANILA_TZ))
        context.setdefault("authorization_notice", current_app.config.get("AUTHORIZATION_NOTICE", ""))
        message = Message(subject=subject, recipients=[to])
        message.html = render_template(f"emails/{template}.html", **context)
        try:
            message.body = render_template(f"emails/{template}.txt", **context)
        except TemplateNotFound:
            message.body = unescape(re.sub(r"<[^>]+>", " ", message.html)).strip()
        mail.send(message)
        return True
    except Exception:
        current_app.logger.exception("Email delivery failed.")
        return False


def record_audit(action, entity_type, entity_id=None, details=None, actor=None):
    if actor is None and has_request_context():
        from flask_login import current_user
        actor = current_user if current_user.is_authenticated else None
    ip = request.remote_addr if has_request_context() else None
    user_agent = request.user_agent.string[:300] if has_request_context() else None
    db.session.add(AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_email=(actor.email if actor else "system")[:255],
        action=action[:80], entity_type=entity_type[:80],
        entity_id=str(entity_id)[:80] if entity_id is not None else None,
        details=details or {}, ip_address=ip, user_agent=user_agent,
    ))


def _otp_digest(challenge_id, code):
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(secret, f"{challenge_id}:{code}".encode("ascii"), hashlib.sha256).hexdigest()


def log_dev_otp(email, code):
    """Log OTP to console in development when SMTP is not configured."""
    if current_app.config.get("APP_ENV") == "development":
        current_app.logger.info(f"[DEV OTP] Email: {email} | Code: {code}")


def issue_email_otp(user):
    now = utcnow()
    db.session.execute(db.select(User.id).where(User.id == user.id).with_for_update())
    latest = db.session.scalar(
        db.select(OTPVerification).where(OTPVerification.user_id == user.id)
        .order_by(OTPVerification.created_at.desc()).limit(1).with_for_update()
    )
    if latest and latest.created_at > now - timedelta(seconds=60):
        return False
    last_hour = db.session.scalar(db.select(db.func.count(OTPVerification.id)).where(
        OTPVerification.user_id == user.id,
        OTPVerification.created_at > now - timedelta(hours=1),
    )) or 0
    if last_hour >= 5:
        return False
    if latest and latest.consumed_at is None:
        latest.consumed_at = now
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = OTPVerification(user_id=user.id, code_digest="pending", expires_at=now + timedelta(minutes=10))
    db.session.add(challenge)
    db.session.flush()
    challenge.code_digest = _otp_digest(challenge.id, code)

    # Log OTP in development when SMTP is not configured
    log_dev_otp(user.email, code)

    # Send OTP email (verification link removed - OTP only). In production, do
    # not invalidate the previous usable code when delivery fails.
    sent = send_email(user.email, "Verify your NU DentalConnect email", "otp", user=user, code=code, expires_minutes=10)
    if not sent and current_app.config.get("APP_ENV") != "development":
        db.session.delete(challenge)
        if latest and latest.consumed_at == now:
            latest.consumed_at = None
        return False
    return sent


def revoke_email_otps(user):
    now = utcnow()
    db.session.execute(db.update(OTPVerification).where(
        OTPVerification.user_id == user.id,
        OTPVerification.consumed_at.is_(None),
    ).values(consumed_at=now))


def verify_email_otp(user, code):
    now = utcnow()
    challenge = db.session.scalar(
        db.select(OTPVerification).where(
            OTPVerification.user_id == user.id,
            OTPVerification.consumed_at.is_(None),
            OTPVerification.expires_at > now,
        ).order_by(OTPVerification.created_at.desc()).limit(1).with_for_update()
    )
    if not challenge or challenge.attempts >= 5:
        return False
    attempts_this_hour = db.session.scalar(db.select(db.func.coalesce(db.func.sum(OTPVerification.attempts), 0)).where(
        OTPVerification.user_id == user.id,
        OTPVerification.created_at > now - timedelta(hours=1),
    )) or 0
    if attempts_this_hour >= 5:
        return False
    expected = _otp_digest(challenge.id, code)
    if not hmac.compare_digest(challenge.code_digest, expected):
        challenge.attempts += 1
        return False
    challenge.attempts += 1
    challenge.consumed_at = now
    user.email_verified = True
    # The route writes the otp_verified audit row through AuditLogger; keeping a
    # second insert here would duplicate the event.
    return True


def notify(user, message):
    db.session.add(Notification(user=user, message=message))


def has_student_conflict(student_id, starts_at, exclude_id=None):
    # One-hour slots; checking adjacent starts prevents overlapping confirmed appointments.
    query = db.select(Appointment).where(
        Appointment.student_id == student_id,
        Appointment.status == "confirmed",
        Appointment.starts_at < starts_at + timedelta(hours=1),
        Appointment.starts_at >= starts_at - timedelta(hours=1),
    )
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    return db.session.scalar(query.with_for_update()) is not None


def has_active_student_booking(student_id, patient_id, starts_at):
    query = db.select(Appointment.id).where(
        Appointment.student_id == student_id,
        Appointment.patient_id == patient_id,
        Appointment.status.in_(["pending", "confirmed", "reschedule_requested"]),
        Appointment.starts_at < starts_at + timedelta(hours=1),
        Appointment.starts_at >= starts_at - timedelta(hours=1),
    )
    return db.session.scalar(query) is not None


def confirm_appointment(appointment):
    # Lock the student row so concurrent confirmations for an otherwise empty schedule serialize.
    db.session.execute(db.select(DentistryStudent.id).where(DentistryStudent.id == appointment.student_id).with_for_update())
    if appointment.starts_at <= utcnow() or has_student_conflict(appointment.student_id, appointment.starts_at, appointment.id):
        return False
    appointment.status = "confirmed"
    db.session.flush()
    return True

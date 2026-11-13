# Mga service function. Functions lang talaga ito, walang
# class, para simple at madaling tawagin sa routes.
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


# Isang lugar lang para sa lahat ng email. Kapag walang SMTP
# config, hindi mag-crash: mag-log lang at False ang sagot.
def send_email(to, subject, template, **context):
    if not current_app.config.get("MAIL_SERVER") or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info("Email not sent: SMTP is not configured (recipient omitted).")
        return False
    try:
        # Kailangan ng email template yung now para sa year sa footer.
        # Default dito para hindi mag-render error kung may nakalimot.
        context.setdefault("now", datetime.now(timezone.utc).astimezone(MANILA_TZ))
        message = Message(subject=subject, recipients=[to])
        message.html = render_template(f"emails/{template}.html", **context)
        try:
            message.body = render_template(f"emails/{template}.txt", **context)
        # Ibang email walang .txt version. Dito yung plain text
        # fallback galing sa HTML.
        except TemplateNotFound:
            message.body = unescape(re.sub(r"<[^>]+>", " ", message.html)).strip()
        mail.send(message)
        return True
    except Exception:
        current_app.logger.exception("Email delivery failed.")
        return False


# Helper para mag-add ng audit row kahit walang request
# context, tulad ng CLI. System ang actor pag wala talagang user.
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


# HMAC gamit yung SECRET_KEY. Kahit mabasa yung database,
# hindi makukuha yung 6-digit code galing sa digest.
def _otp_digest(challenge_id, code):
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(secret, f"{challenge_id}:{code}".encode("ascii"), hashlib.sha256).hexdigest()


# Sa development lang ito. Walang SMTP sa local, kaya sa
# console nakalagay yung code para makapag-test.
def log_dev_otp(email, code):
    if current_app.config.get("APP_ENV") == "development":
        current_app.logger.info(f"[DEV OTP] Email: {email} | Code: {code}")


# Gumagawa ng bagong OTP. May limit: 60 seconds bago
# makahingi ulit, at max 5 per hour per user.
def issue_email_otp(user):
    now = utcnow()
    # Lock muna yung user row para hindi sabay mag-generate ng
    # code kung dalawang tab yung nag-request.
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

    log_dev_otp(user.email, code)

    # Sa production, kapag hindi nasend yung email, tinatanggal
    # ko yung bagong challenge. Sa dev, hinahayaan ko para may code.
    sent = send_email(user.email, "Verify your NU DentalConnect email", "otp", user=user, code=code, expires_minutes=10)
    if not sent and current_app.config.get("APP_ENV") != "development":
        db.session.delete(challenge)
        if latest and latest.consumed_at == now:
            latest.consumed_at = None
        return False
    return sent


# Tinatawag pag nagpalit ng email. Yung unused codes, expired
# na agad para hindi magamit sa lumang address.
def revoke_email_otps(user):
    now = utcnow()
    db.session.execute(db.update(OTPVerification).where(
        OTPVerification.user_id == user.id,
        OTPVerification.consumed_at.is_(None),
    ).values(consumed_at=now))


# Hinahanap yung pinakabagong unused at hindi pa expired na
# code. Limit: 5 attempts per code at 5 per hour.
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
    # compare_digest para hindi malaman kung saang part nagkamali
    # (timing attack). Maling code, dagdagan yung attempts.
    if not hmac.compare_digest(challenge.code_digest, expected):
        challenge.attempts += 1
        return False
    challenge.attempts += 1
    challenge.consumed_at = now
    user.email_verified = True
    return True


# Pasimple lang: isang row sa notifications. Ang commit,
# sa route na.
def notify(user, message):
    db.session.add(Notification(user=user, message=message))


# One-hour slots ito. Titingnan ko yung katabi para hindi
# mag-overlap yung confirmed appointments ng student.
def has_student_conflict(student_id, starts_at, exclude_id=None):
    query = db.select(Appointment).where(
        Appointment.student_id == student_id,
        Appointment.status == "confirmed",
        Appointment.starts_at < starts_at + timedelta(hours=1),
        Appointment.starts_at >= starts_at - timedelta(hours=1),
    )
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    return db.session.scalar(query.with_for_update()) is not None


# Para hindi makapag-request yung patient ng doble sa
# kaparehong oras, kahit pending pa lang yung isa.
def has_active_student_booking(student_id, patient_id, starts_at):
    query = db.select(Appointment.id).where(
        Appointment.student_id == student_id,
        Appointment.patient_id == patient_id,
        Appointment.status.in_(["pending", "confirmed", "reschedule_requested"]),
        Appointment.starts_at < starts_at + timedelta(hours=1),
        Appointment.starts_at >= starts_at - timedelta(hours=1),
    )
    return db.session.scalar(query) is not None


# Lock yung student row bago mag-confirm. Kung sabay kasi
# ang dalawang confirm, puwedeng magka-conflict yung slot.
def confirm_appointment(appointment):
    db.session.execute(db.select(DentistryStudent.id).where(DentistryStudent.id == appointment.student_id).with_for_update())
    # Bawal mag-confirm ng nakalipas na oras o may ka-conflict.
    if appointment.starts_at <= utcnow() or has_student_conflict(appointment.student_id, appointment.starts_at, appointment.id):
        return False
    appointment.status = "confirmed"
    db.session.flush()
    return True

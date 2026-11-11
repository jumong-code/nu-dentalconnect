"""
Audit logging service for NU DentalConnect.

Centralizes all audit event creation with single-purpose methods.
Ensures consistent formatting, Manila timezone display, and device identification.
No raw secrets, OTPs, passwords, or tokens are ever stored.
"""
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from flask import has_request_context, request
from user_agents import parse as parse_user_agent

from .extensions import db
from .models import AuditLog, User, utcnow
from .time_utils import MANILA_TZ


# Device ID cookie name
DEVICE_ID_COOKIE = "dc_device_id"
DEVICE_ID_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


class DeviceInfo:
    """Parses User-Agent and manages first-party device identification cookie."""

    _ua_cache = {}

    @classmethod
    def from_request(cls, request_obj=None) -> "DeviceInfo":
        """Create DeviceInfo from current request context or passed request object."""
        # Use passed request object if provided, otherwise fall back to global request
        if request_obj is not None:
            ua_string = request_obj.user_agent.string if request_obj.user_agent else ""
            device_id = request_obj.cookies.get(DEVICE_ID_COOKIE) if hasattr(request_obj, 'cookies') else None
        elif has_request_context():
            ua_string = request.user_agent.string or ""
            device_id = request.cookies.get(DEVICE_ID_COOKIE)
        else:
            return cls("unknown", "unknown", "unknown", None)

        # Parse User-Agent for browser/OS/device-type label
        browser, os, device_type = cls._parse_ua(ua_string)

        return cls(browser, os, device_type, device_id)

    @classmethod
    def _parse_ua(cls, ua_string: str) -> tuple[str, str, str]:
        """Parse User-Agent string into browser, OS, device-type."""
        if not ua_string:
            return "unknown", "unknown", "unknown"

        # Simple cache for repeated UAs
        if ua_string in cls._ua_cache:
            return cls._ua_cache[ua_string]

        try:
            ua = parse_user_agent(ua_string)
            browser = f"{ua.browser.family} {ua.browser.version_string}" if ua.browser.family else "unknown"
            os = f"{ua.os.family} {ua.os.version_string}" if ua.os.family else "unknown"
            device_type = "mobile" if ua.is_mobile else ("tablet" if ua.is_tablet else ("bot" if ua.is_bot else "desktop"))
        except Exception:
            browser, os, device_type = "unknown", "unknown", "unknown"

        cls._ua_cache[ua_string] = (browser, os, device_type)
        return browser, os, device_type

    def __init__(self, browser: str, os: str, device_type: str, device_id: Optional[str]):
        self.browser = browser[:100]
        self.os = os[:100]
        self.device_type = device_type[:20]
        self.device_id = device_id

    def to_label(self) -> str:
        """Human-readable device label for audit display."""
        return f"{self.browser} / {self.os} / {self.device_type}"

    def to_details(self) -> dict:
        """Structured details for audit JSON column (hashed device ID only)."""
        return {
            "label": self.to_label(),
            "browser": self.browser,
            "os": self.os,
            "device_type": self.device_type,
            "device_id_hash": self._hash_device_id(self.device_id) if self.device_id else None,
        }

    @staticmethod
    def _hash_device_id(device_id: str) -> str:
        """Hash device ID for storage (never store raw)."""
        return hashlib.sha256(device_id.encode()).hexdigest()[:16]

    @staticmethod
    def generate_device_id() -> str:
        """Generate a new random device ID."""
        import secrets
        return secrets.token_urlsafe(32)

    def set_cookie(self, response, secure: bool = False) -> None:
        """Set the HttpOnly first-party device ID cookie when the request has none."""
        if self.device_id is None:
            new_id = self.generate_device_id()
            response.set_cookie(
                DEVICE_ID_COOKIE,
                new_id,
                max_age=DEVICE_ID_MAX_AGE,
                httponly=True,
                secure=secure,
                samesite="Lax",
                path="/",
            )


class AuditLogger:
    """
    Single-purpose audit logging methods.

    All methods create an AuditLog row with consistent structure:
    - actor_user_id (FK, SET NULL on user delete)
    - actor_email (snapshot, never null)
    - action (standardized verb)
    - entity_type / entity_id
    - details (JSON, no secrets)
    - ip_address, user_agent, device_info
    - created_at (UTC, displayed in Manila via template filter)

    Failed-login and other non-transactional events commit immediately.
    """

    # Standardized action verbs
    ACTION_LOGIN_SUCCESS = "login_success"
    ACTION_LOGIN_FAILURE = "login_failure"
    ACTION_LOGIN_LOCKOUT = "login_lockout"
    ACTION_LOGOUT = "logout"
    ACTION_REGISTER = "account_registered"
    ACTION_OTP_SENT = "otp_sent"
    ACTION_OTP_VERIFIED = "otp_verified"
    ACTION_OTP_FAILED = "otp_failed"
    ACTION_OTP_RESENT = "otp_resent"
    ACTION_PASSWORD_CHANGED = "password_changed"
    ACTION_PASSWORD_RESET = "password_reset"
    ACTION_PASSWORD_RESET_REQUESTED = "password_reset_requested"
    ACTION_PASSWORD_ADMIN_SET = "password_admin_set"
    ACTION_PROFILE_UPDATED = "profile_updated"
    ACTION_EMAIL_CHANGED = "email_changed"
    ACTION_AVATAR_UPLOADED = "avatar_uploaded"
    ACTION_AVATAR_REMOVED = "avatar_removed"
    ACTION_LISTING_CREATED = "listing_created"
    ACTION_LISTING_UPDATED = "listing_updated"
    ACTION_LISTING_STATUS_CHANGED = "listing_status_changed"
    ACTION_LISTING_DELETED = "listing_deleted"
    ACTION_COVER_UPLOADED = "cover_uploaded"
    ACTION_COVER_REMOVED = "cover_removed"
    ACTION_TEMPLATE_CREATED = "template_created"
    ACTION_TEMPLATE_DELETED = "template_deleted"
    ACTION_APPLICATION_CREATED = "application_created"
    ACTION_APPLICATION_DECISION = "application_decision"
    ACTION_APPLICATION_WITHDRAWN = "application_withdrawn"
    ACTION_APPOINTMENT_REQUESTED = "appointment_requested"
    ACTION_APPOINTMENT_CANCELLED = "appointment_cancelled"
    ACTION_APPOINTMENT_RESCHEDULED = "appointment_rescheduled"
    ACTION_APPOINTMENT_PROPOSED = "appointment_proposed"
    ACTION_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    ACTION_APPOINTMENT_REJECTED = "appointment_rejected"
    ACTION_APPOINTMENT_COMPLETED = "appointment_completed"
    ACTION_APPOINTMENT_DELETED = "appointment_deleted"
    ACTION_ADMIN_USER_APPROVED = "admin_user_approved"
    ACTION_ADMIN_USER_DELETED = "admin_user_deleted"
    ACTION_ADMIN_LISTING_DELETED = "admin_listing_deleted"
    ACTION_ADMIN_APPOINTMENT_DELETED = "admin_appointment_deleted"
    ACTION_ADMIN_USER_TOGGLE = "admin_user_toggle"
    ACTION_ADMIN_LISTING_CLOSED = "admin_listing_closed"
    ACTION_PROFILE_VIEWED = "profile_viewed"
    ACTION_NOTIFICATION_READ = "notification_read"
    ACTION_STUDENT_APPROVED = "student_approved"
    ACTION_STUDENT_REJECTED = "student_rejected"

    def __init__(self):
        self._device_info = None

    def _get_actor_info(self, actor: Optional[User] = None, user: Optional[User] = None, viewer: Optional[User] = None) -> tuple[Optional[int], str]:
        """Extract actor_user_id and actor_email from various parameter names."""
        # Support multiple parameter names for backward compatibility
        actual_actor = actor or user or viewer
        if actual_actor is not None:
            return actual_actor.id, actual_actor.email[:255]
        if has_request_context():
            from flask_login import current_user
            if current_user.is_authenticated:
                return current_user.id, current_user.email[:255]
        return None, "system"

    def _get_request_context(self, device: Optional[DeviceInfo] = None) -> tuple[Optional[str], Optional[str], DeviceInfo]:
        """Extract IP, User-Agent, and DeviceInfo from request."""
        if not has_request_context():
            return None, None, device or DeviceInfo("unknown", "unknown", "unknown", None)

        ip = request.remote_addr
        ua = request.user_agent.string[:300] if request.user_agent.string else None
        # Use passed device or create new one from current request
        dev = device or DeviceInfo.from_request()
        return ip, ua, dev

    def _commit_now(self) -> None:
        """Immediate commit for non-transactional events (e.g., failed login)."""
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Log but don't raise - audit must not break the main flow
            import logging
            logging.getLogger(__name__).exception("Audit commit failed")

    def _add_log(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        details: Optional[dict] = None,
        actor: Optional[User] = None,
        user: Optional[User] = None,
        viewer: Optional[User] = None,
        device: Optional[DeviceInfo] = None,
        commit_now: bool = False,
        **extra_details
    ) -> AuditLog:
        """Internal: create and add AuditLog row."""
        actor_id, actor_email = self._get_actor_info(actor, user, viewer)
        ip, ua, dev = self._get_request_context(device)

        log_details = details or {}
        # Merge any extra details passed as kwargs
        log_details.update(extra_details)
        log_details["device"] = dev.to_details()

        log = AuditLog(
            actor_user_id=actor_id,
            actor_email=actor_email,
            action=action[:80],
            entity_type=entity_type[:80],
            entity_id=str(entity_id)[:80] if entity_id is not None else None,
            details=log_details,
            ip_address=ip,
            user_agent=ua,
        )
        db.session.add(log)

        if commit_now:
            self._commit_now()

        return log

    # ========== Auth events ==========

    def login_success(self, user: User = None, actor: User = None, device: DeviceInfo = None, remember: bool = False, **kwargs) -> AuditLog:
        """Successful login."""
        u = user or actor
        return self._add_log(self.ACTION_LOGIN_SUCCESS, "user", str(u.id) if u else None, {"remember": remember}, actor=u, device=device)

    def login_failure(self, email: str = None, device: DeviceInfo = None, reason: str = "invalid_credentials", **kwargs) -> AuditLog:
        """Failed login - NEVER reveals whether account exists."""
        # Use a generic email snapshot that doesn't leak existence
        display_email = email[:255] if email else "unknown"
        return self._add_log(
            self.ACTION_LOGIN_FAILURE,
            "user",
            None,
            {"reason": reason, "email": display_email},
            device=device,
            commit_now=True,  # Non-transactional
        )

    def login_lockout(self, email: str) -> AuditLog:
        """Account lockout due to failed attempts."""
        return self._add_log(
            self.ACTION_LOGIN_LOCKOUT,
            "user",
            None,
            {"reason": "too_many_failures"},
            commit_now=True,
        )

    def logout(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """User logout."""
        u = user or actor
        return self._add_log(self.ACTION_LOGOUT, "user", str(u.id) if u else None, actor=u, device=device)

    def account_registered(self, user: User = None, actor: User = None, role: str = None, device: DeviceInfo = None, success: bool = True, **kwargs) -> AuditLog:
        """New account registration."""
        u = user or actor
        return self._add_log(self.ACTION_REGISTER, "user", str(u.id) if u else None, {"role": role, "success": success}, actor=u, device=device)

    # ========== OTP events ==========

    def otp_sent(self, user: User = None, actor: User = None, purpose: str = "verification", device: DeviceInfo = None, trigger: str = None, **kwargs) -> AuditLog:
        """OTP email sent."""
        u = user or actor
        details = {"purpose": purpose}
        if trigger:
            details["trigger"] = trigger
        return self._add_log(self.ACTION_OTP_SENT, "user", str(u.id) if u else None, details, actor=u, device=device)

    def otp_verified(self, user: User = None, actor: User = None, method: str = "code", device: DeviceInfo = None, **kwargs) -> AuditLog:
        """OTP successfully verified."""
        u = user or actor
        return self._add_log(self.ACTION_OTP_VERIFIED, "user", str(u.id) if u else None, {"method": method}, actor=u, device=device)

    def otp_failed(self, email: str = None, user: User = None, actor: User = None, device: DeviceInfo = None, reason: str = "invalid_code", **kwargs) -> AuditLog:
        """OTP verification failed."""
        # Support both calling patterns: otp_failed(user=..., reason=...) and otp_failed(email=..., reason=...)
        u = user or actor
        if u is not None:
            entity_id = str(u.id)
            actor_param = u
        else:
            entity_id = None
            actor_param = None
        return self._add_log(
            self.ACTION_OTP_FAILED,
            "user",
            entity_id,
            {"reason": reason, "email": email[:255] if email else None},
            actor=actor_param,
            device=device,
            commit_now=True,
        )

    def otp_resent(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """OTP resent."""
        u = user or actor
        return self._add_log(self.ACTION_OTP_RESENT, "user", str(u.id) if u else None, actor=u, device=device)

    def email_verified(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Email verification completed."""
        u = user or actor
        return self._add_log(self.ACTION_OTP_VERIFIED, "user", str(u.id) if u else None, {"method": "code"}, actor=u, device=device)

    # ========== Password events ==========

    def password_changed(self, user: User = None, actor: User = None, device: DeviceInfo = None, method: str = "user_initiated", **kwargs) -> AuditLog:
        """User changed own password."""
        u = user or actor
        return self._add_log(self.ACTION_PASSWORD_CHANGED, "user", str(u.id) if u else None, {"method": method}, actor=u, device=device)

    def password_reset(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Password reset via email link."""
        u = user or actor
        return self._add_log(self.ACTION_PASSWORD_RESET, "user", str(u.id) if u else None, actor=u, device=device)

    def password_reset_requested(self, user: User = None, email: str = None, device: DeviceInfo = None, user_not_found: bool = False, **kwargs) -> AuditLog:
        """Password reset requested."""
        if user is not None:
            entity_id = str(user.id)
            actor_param = user
        else:
            entity_id = None
            actor_param = None
        return self._add_log(
            self.ACTION_PASSWORD_RESET_REQUESTED,
            "user",
            entity_id,
            {"email": email[:255] if email else None, "user_not_found": user_not_found},
            actor=actor_param,
            device=device,
        )

    def password_admin_set(self, actor: User = None, target_user: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Admin set/reset another user's password."""
        return self._add_log(
            self.ACTION_PASSWORD_ADMIN_SET,
            "user",
            str(target_user.id) if target_user else None,
            {"target_email": target_user.email[:255] if target_user else None},
            actor=actor,
            device=device,
        )

    # ========== Profile events ==========

    def profile_updated(self, actor: User = None, fields: list[str] = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Profile information updated."""
        return self._add_log(self.ACTION_PROFILE_UPDATED, "user", str(actor.id) if actor else None, {"fields": fields or []}, actor=actor, device=device)

    def email_changed(self, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Email address changed (triggers re-verification)."""
        return self._add_log(self.ACTION_EMAIL_CHANGED, "user", str(actor.id) if actor else None, {"verification_required": True}, actor=actor, device=device)

    def avatar_uploaded(self, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Avatar image uploaded."""
        return self._add_log(self.ACTION_AVATAR_UPLOADED, "user", str(actor.id) if actor else None, actor=actor, device=device)

    def avatar_removed(self, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Avatar image removed."""
        return self._add_log(self.ACTION_AVATAR_REMOVED, "user", str(actor.id) if actor else None, actor=actor, device=device)

    # ========== Listing events ==========

    def listing_created(self, actor: User = None, listing_id: int = None, status: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """New recruitment listing created."""
        return self._add_log(self.ACTION_LISTING_CREATED, "listing", str(listing_id) if listing_id else None, {"status": status}, actor=actor, device=device)

    def listing_updated(self, actor: User = None, listing_id: int = None, status: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Listing content updated."""
        return self._add_log(self.ACTION_LISTING_UPDATED, "listing", str(listing_id) if listing_id else None, {"status": status}, actor=actor, device=device)

    def listing_status_changed(self, actor: User = None, listing_id: int = None, status: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Listing status transition."""
        return self._add_log(self.ACTION_LISTING_STATUS_CHANGED, "listing", str(listing_id) if listing_id else None, {"status": status}, actor=actor, device=device)

    def listing_deleted(self, actor: User = None, listing_id: int = None, title: str = None, applications_cascaded: int = 0, appointments_unlinked: int = 0, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Listing deleted (by owner or admin)."""
        return self._add_log(
            self.ACTION_LISTING_DELETED,
            "listing",
            str(listing_id) if listing_id else None,
            {"title": title, "applications_cascaded": applications_cascaded, "appointments_unlinked": appointments_unlinked},
            actor=actor,
            device=device,
        )

    def cover_uploaded(self, actor: User = None, listing_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Listing cover image uploaded."""
        return self._add_log(self.ACTION_COVER_UPLOADED, "listing", str(listing_id) if listing_id else None, actor=actor, device=device)

    def cover_removed(self, actor: User = None, listing_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Listing cover image removed."""
        return self._add_log(self.ACTION_COVER_REMOVED, "listing", str(listing_id) if listing_id else None, actor=actor, device=device)

    # ========== Template events ==========

    def template_created(self, actor: User = None, template_id: int = None, name: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Saved listing template created."""
        return self._add_log(self.ACTION_TEMPLATE_CREATED, "listing_template", str(template_id) if template_id else None, {"name": name}, actor=actor, device=device)

    def template_deleted(self, actor: User = None, template_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Saved listing template deleted."""
        return self._add_log(self.ACTION_TEMPLATE_DELETED, "listing_template", str(template_id) if template_id else None, actor=actor, device=device)

    # ========== Application events ==========

    def application_created(self, actor: User = None, application_id: int = None, listing_id: int = None, listing_title: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Patient application submitted."""
        return self._add_log(self.ACTION_APPLICATION_CREATED, "application", str(application_id) if application_id else None, {"listing_id": listing_id, "listing_title": listing_title}, actor=actor, device=device)

    def application_decision(self, actor: User = None, application_id: int = None, decision: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Application accepted/rejected."""
        return self._add_log(self.ACTION_APPLICATION_DECISION, "application", str(application_id) if application_id else None, {"status": decision}, actor=actor, device=device)

    def application_withdrawn(self, actor: User = None, application_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Patient withdrew application."""
        return self._add_log(self.ACTION_APPLICATION_WITHDRAWN, "application", str(application_id) if application_id else None, actor=actor, device=device)

    # ========== Appointment events ==========

    def appointment_requested(self, actor: User = None, appointment_id: int = None, listing_id: int = None, listing_title: str = None, starts_at: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Patient requested appointment."""
        return self._add_log(self.ACTION_APPOINTMENT_REQUESTED, "appointment", str(appointment_id) if appointment_id else None, {"listing_id": listing_id, "listing_title": listing_title, "starts_at": starts_at}, actor=actor, device=device)

    def appointment_cancelled(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Appointment cancelled."""
        return self._add_log(self.ACTION_APPOINTMENT_CANCELLED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    def appointment_rescheduled(self, actor: User = None, appointment_id: int = None, proposed_at: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Patient requested reschedule or student proposed new time."""
        return self._add_log(self.ACTION_APPOINTMENT_RESCHEDULED, "appointment", str(appointment_id) if appointment_id else None, {"proposed_at": proposed_at}, actor=actor, device=device)

    def appointment_proposed(self, actor: User = None, appointment_id: int = None, proposed_at: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Student proposed alternative time."""
        return self._add_log(self.ACTION_APPOINTMENT_PROPOSED, "appointment", str(appointment_id) if appointment_id else None, {"proposed_at": proposed_at}, actor=actor, device=device)

    def appointment_confirmed(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Appointment confirmed (by student or patient accepting proposal)."""
        return self._add_log(self.ACTION_APPOINTMENT_CONFIRMED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    def appointment_rejected(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Appointment rejected."""
        return self._add_log(self.ACTION_APPOINTMENT_REJECTED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    def appointment_completed(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Appointment marked complete."""
        return self._add_log(self.ACTION_APPOINTMENT_COMPLETED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    def appointment_deleted(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Appointment hard-deleted (patient non-confirmed, admin any)."""
        return self._add_log(self.ACTION_APPOINTMENT_DELETED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    # ========== Admin events ==========

    def admin_user_approved(self, admin: User = None, actor: User = None, student_user: User = None, target_user: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Admin approved a pending student."""
        a = admin or actor
        s = student_user or target_user
        return self._add_log(
            self.ACTION_ADMIN_USER_APPROVED,
            "user",
            str(s.id) if s else None,
            {"student_email": s.email[:255] if s else None},
            actor=a,
            device=device,
        )

    def student_approved(self, actor: User = None, student: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Student approved by an administrator (approval-queue event)."""
        return self._add_log(
            self.ACTION_STUDENT_APPROVED,
            "user",
            str(student.id) if student else None,
            {"student_email": student.email[:255] if student else None, "approval_status": "approved"},
            actor=actor,
            device=device,
        )

    def student_rejected(self, actor: User = None, student: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Student rejected by admin."""
        return self._add_log(
            self.ACTION_STUDENT_REJECTED,
            "user",
            str(student.id) if student else None,
            {"student_email": student.email[:255] if student else None},
            actor=actor,
            device=device,
        )

    def admin_user_deleted(self, admin: User = None, actor: User = None, target_user: User = None, role: str = None, email: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Admin deleted a user account."""
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_USER_DELETED,
            "user",
            str(target_user.id) if target_user else None,
            {"role": role, "email": email[:255] if email else (target_user.email[:255] if target_user else None)},
            actor=a,
            device=device,
        )

    def admin_listing_deleted(self, admin: User = None, actor: User = None, listing_id: int = None, title: str = None, applications_cascaded: int = 0, appointments_unlinked: int = 0, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Admin deleted a listing."""
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_LISTING_DELETED,
            "listing",
            str(listing_id) if listing_id else None,
            {"title": title, "applications_cascaded": applications_cascaded, "appointments_unlinked": appointments_unlinked},
            actor=a,
            device=device,
        )

    def admin_appointment_deleted(self, admin: User = None, actor: User = None, appointment_id: int = None, listing_id: Optional[int] = None, patient_id: int = None, student_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Admin deleted an appointment."""
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_APPOINTMENT_DELETED,
            "appointment",
            str(appointment_id) if appointment_id else None,
            {"listing_id": listing_id, "patient_id": patient_id, "student_id": student_id},
            actor=a,
            device=device,
        )

    def admin_listing_closed(self, admin: User = None, actor: User = None, listing_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Admin closed a listing from the oversight view."""
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_LISTING_CLOSED,
            "listing",
            str(listing_id) if listing_id else None,
            {"status": "closed"},
            actor=a,
            device=device,
        )

    def admin_user_toggle(self, admin: User = None, actor: User = None, target_user: User = None, is_active: bool = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Admin activated/deactivated a user."""
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_USER_TOGGLE,
            "user",
            str(target_user.id) if target_user else None,
            {"is_active": is_active, "target_email": target_user.email[:255] if target_user else None},
            actor=a,
            device=device,
        )

    def notification_read(self, actor: User = None, notification_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """In-app notification marked as read."""
        return self._add_log(
            self.ACTION_NOTIFICATION_READ,
            "notification",
            str(notification_id) if notification_id else None,
            actor=actor,
            device=device,
        )

    # ========== Profile view (privacy boundary) ==========

    def profile_viewed(self, viewer: User = None, target_user: User = None, allowed: bool = True, device: DeviceInfo = None, **kwargs) -> AuditLog:
        """Profile view attempt (logs both allowed and denied for privacy audit)."""
        return self._add_log(
            self.ACTION_PROFILE_VIEWED,
            "user",
            str(target_user.id) if target_user else None,
            {"viewer_id": viewer.id if viewer else None, "viewer_role": viewer.role if viewer else None, "target_role": target_user.role if target_user else None, "allowed": allowed},
            actor=viewer,
            device=device,
        )


# Singleton instance
audit_logger = AuditLogger()


def get_device_info(request_obj=None) -> DeviceInfo:
    """Get DeviceInfo from a Flask request object or the current request context."""
    return DeviceInfo.from_request(request_obj)

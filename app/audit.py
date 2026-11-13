# Audit logging. Nandito lahat ng event na gusto kong maitala,
# isang method kada action para pareho palagi ang format.
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from flask import has_request_context, request
from user_agents import parse as parse_user_agent

from .extensions import db
from .models import AuditLog, User, utcnow
from .time_utils import MANILA_TZ


# Name at tagal ng device cookie. Isang taon bago mawala.
DEVICE_ID_COOKIE = "dc_device_id"
DEVICE_ID_MAX_AGE = 365 * 24 * 60 * 60


# Kinukuha yung browser at OS galing sa User-Agent, tapos may
# sarili tayong cookie para makilala yung parehong device.
class DeviceInfo:

    # Cache ng na-parse nang UA. Madalas paulit-ulit yung parehong
    # user agent, sayang kung i-parse ulit.
    _ua_cache = {}

    # Kunin sa request context, o sa pinasang request object.
    @classmethod
    def from_request(cls, request_obj=None) -> "DeviceInfo":
        if request_obj is not None:
            ua_string = request_obj.user_agent.string if request_obj.user_agent else ""
            device_id = request_obj.cookies.get(DEVICE_ID_COOKIE) if hasattr(request_obj, 'cookies') else None
        elif has_request_context():
            ua_string = request.user_agent.string or ""
            device_id = request.cookies.get(DEVICE_ID_COOKIE)
        else:
            return cls("unknown", "unknown", "unknown", None)

        browser, os, device_type = cls._parse_ua(ua_string)

        return cls(browser, os, device_type, device_id)

    # Naka-base sa is_mobile at is_tablet yung label. Pag error,
    # unknown na lang, hindi ko papabagsakin yung request.
    @classmethod
    def _parse_ua(cls, ua_string: str) -> tuple[str, str, str]:
        if not ua_string:
            return "unknown", "unknown", "unknown"

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

    # Hinahati ko yung haba ng bawat field para hindi lumampas
    # sa column size sa database.
    def __init__(self, browser: str, os: str, device_type: str, device_id: Optional[str]):
        self.browser = browser[:100]
        self.os = os[:100]
        self.device_type = device_type[:20]
        self.device_id = device_id

    # Text na ipinapakita sa admin audit table.
    def to_label(self) -> str:
        return f"{self.browser} / {self.os} / {self.device_type}"

    # Details para sa JSON column. Hash lang ang device id,
    # hindi yung raw value na nasa browser.
    def to_details(self) -> dict:
        return {
            "label": self.to_label(),
            "browser": self.browser,
            "os": self.os,
            "device_type": self.device_type,
            "device_id_hash": self._hash_device_id(self.device_id) if self.device_id else None,
        }

    # Truncated SHA-256. Sapat para makilala yung parehong device,
    # pero hindi na mababalik sa original.
    @staticmethod
    def _hash_device_id(device_id: str) -> str:
        return hashlib.sha256(device_id.encode()).hexdigest()[:16]

    # Random at URL-safe. Ito yung ilalagay sa cookie.
    @staticmethod
    def generate_device_id() -> str:
        import secrets
        return secrets.token_urlsafe(32)

    # HttpOnly para hindi mabasa ng JavaScript. Lax yung
    # same-site para gumana pa rin sa normal na navigation.
    def set_cookie(self, response, secure: bool = False) -> None:
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


# Isang class para sa lahat ng audit event. Nasa _add_log
# yung common na gawain para hindi paulit-ulit.
class AuditLogger:

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

    # Wala pang laman sa simula. Hindi pa ito nagagamit sa
    # ibang method.
    def __init__(self):
        self._device_info = None

    # Tatanggapin ko yung actor, user, o viewer na parameter para
    # hindi na kailangan baguhin yung mga lumang tawag sa routes.
    def _get_actor_info(self, actor: Optional[User] = None, user: Optional[User] = None, viewer: Optional[User] = None) -> tuple[Optional[int], str]:
        actual_actor = actor or user or viewer
        if actual_actor is not None:
            return actual_actor.id, actual_actor.email[:255]
        if has_request_context():
            from flask_login import current_user
            if current_user.is_authenticated:
                return current_user.id, current_user.email[:255]
        return None, "system"

    # IP at user agent galing sa request. Pag walang request,
    # unknown device na lang ang ibabalik.
    def _get_request_context(self, device: Optional[DeviceInfo] = None) -> tuple[Optional[str], Optional[str], DeviceInfo]:
        if not has_request_context():
            return None, None, device or DeviceInfo("unknown", "unknown", "unknown", None)

        ip = request.remote_addr
        ua = request.user_agent.string[:300] if request.user_agent.string else None
        dev = device or DeviceInfo.from_request()
        return ip, ua, dev

    # Kapag pumalya yung commit, rollback at log lang. Hindi ko
    # papabagsakin yung main flow dahil sa audit.
    def _commit_now(self) -> None:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            import logging
            logging.getLogger(__name__).exception("Audit commit failed")

    # Dito dumadaan lahat. Pinipiga ko yung haba ng fields para
    # hindi lumampas sa column, tapos dinadagdag ko yung device.
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
        actor_id, actor_email = self._get_actor_info(actor, user, viewer)
        ip, ua, dev = self._get_request_context(device)

        log_details = details or {}
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


    # Kung sino yung nag-login, at kung galing sa remember
    # checkbox yung session.
    def login_success(self, user: User = None, actor: User = None, device: DeviceInfo = None, remember: bool = False, **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_LOGIN_SUCCESS, "user", str(u.id) if u else None, {"remember": remember}, actor=u, device=device)

    # Hindi dapat malaman ng anonymous kung may account sa email
    # na yun, kaya generic ang sagot at dito lang yung reason.
    def login_failure(self, email: str = None, device: DeviceInfo = None, reason: str = "invalid_credentials", **kwargs) -> AuditLog:
        display_email = email[:255] if email else "unknown"
        return self._add_log(
            self.ACTION_LOGIN_FAILURE,
            "user",
            None,
            {"reason": reason, "email": display_email},
            device=device,
            commit_now=True,
        )

    # Sunod-sunod na maling password. Naka-commit agad kasi
    # kailangan maitala kahit mag-error pa yung request.
    def login_lockout(self, email: str) -> AuditLog:
        return self._add_log(
            self.ACTION_LOGIN_LOCKOUT,
            "user",
            None,
            {"reason": "too_many_failures"},
            commit_now=True,
        )

    # Pag sign out, naka-record din para may trail ng session.
    def logout(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_LOGOUT, "user", str(u.id) if u else None, actor=u, device=device)

    # Bagong account, kasama yung role at kung successful.
    def account_registered(self, user: User = None, actor: User = None, role: str = None, device: DeviceInfo = None, success: bool = True, **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_REGISTER, "user", str(u.id) if u else None, {"role": role, "success": success}, actor=u, device=device)


    # Nagpadala ng OTP email. purpose ang nagsasabi kung
    # verification o iba.
    def otp_sent(self, user: User = None, actor: User = None, purpose: str = "verification", device: DeviceInfo = None, trigger: str = None, **kwargs) -> AuditLog:
        u = user or actor
        details = {"purpose": purpose}
        if trigger:
            details["trigger"] = trigger
        return self._add_log(self.ACTION_OTP_SENT, "user", str(u.id) if u else None, details, actor=u, device=device)

    # Tama yung code at nagamit na.
    def otp_verified(self, user: User = None, actor: User = None, method: str = "code", device: DeviceInfo = None, **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_OTP_VERIFIED, "user", str(u.id) if u else None, {"method": method}, actor=u, device=device)

    # Maling o expired na code. Sinusuportahan yung dalawang
    # style ng tawag: may user, o email lang.
    def otp_failed(self, email: str = None, user: User = None, actor: User = None, device: DeviceInfo = None, reason: str = "invalid_code", **kwargs) -> AuditLog:
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

    # Bagong code pag na-expire o hindi dumating yung una.
    def otp_resent(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_OTP_RESENT, "user", str(u.id) if u else None, actor=u, device=device)

    # Kapareho ng otp_verified. Mas malinaw lang pangalan
    # para sa route ng verification.
    def email_verified(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_OTP_VERIFIED, "user", str(u.id) if u else None, {"method": "code"}, actor=u, device=device)


    # User mismo nagpalit ng password sa profile page.
    def password_changed(self, user: User = None, actor: User = None, device: DeviceInfo = None, method: str = "user_initiated", **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_PASSWORD_CHANGED, "user", str(u.id) if u else None, {"method": method}, actor=u, device=device)

    # Na-reset via email link.
    def password_reset(self, user: User = None, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        u = user or actor
        return self._add_log(self.ACTION_PASSWORD_RESET, "user", str(u.id) if u else None, actor=u, device=device)

    # May nag-request ng reset, kasama yung kaso na wala
    # talagang account para makita sa audit.
    def password_reset_requested(self, user: User = None, email: str = None, device: DeviceInfo = None, user_not_found: bool = False, **kwargs) -> AuditLog:
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

    # Admin ang nag-set. Wala syempre yung password sa details.
    def password_admin_set(self, actor: User = None, target_user: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(
            self.ACTION_PASSWORD_ADMIN_SET,
            "user",
            str(target_user.id) if target_user else None,
            {"target_email": target_user.email[:255] if target_user else None},
            actor=actor,
            device=device,
        )


    # Nag-save ng profile. Listahan lang ng fields ang nakalagay.
    def profile_updated(self, actor: User = None, fields: list[str] = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_PROFILE_UPDATED, "user", str(actor.id) if actor else None, {"fields": fields or []}, actor=actor, device=device)

    # Bagong email, kailangan ulit i-verify.
    def email_changed(self, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_EMAIL_CHANGED, "user", str(actor.id) if actor else None, {"verification_required": True}, actor=actor, device=device)

    # Bagong avatar na na-upload.
    def avatar_uploaded(self, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_AVATAR_UPLOADED, "user", str(actor.id) if actor else None, actor=actor, device=device)

    # Tinanggal yung avatar.
    def avatar_removed(self, actor: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_AVATAR_REMOVED, "user", str(actor.id) if actor else None, actor=actor, device=device)


    # Bagong listing galing sa student, kasama yung status.
    def listing_created(self, actor: User = None, listing_id: int = None, status: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_LISTING_CREATED, "listing", str(listing_id) if listing_id else None, {"status": status}, actor=actor, device=device)

    # In-edit yung listing, kasama yung status pagkatapos.
    def listing_updated(self, actor: User = None, listing_id: int = None, status: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_LISTING_UPDATED, "listing", str(listing_id) if listing_id else None, {"status": status}, actor=actor, device=device)

    # Nagpalit ng status: draft, published, o closed.
    def listing_status_changed(self, actor: User = None, listing_id: int = None, status: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_LISTING_STATUS_CHANGED, "listing", str(listing_id) if listing_id else None, {"status": status}, actor=actor, device=device)

    # Kasama yung bilang ng applications at appointments na
    # naapektuhan, para may record ng cascade.
    def listing_deleted(self, actor: User = None, listing_id: int = None, title: str = None, applications_cascaded: int = 0, appointments_unlinked: int = 0, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(
            self.ACTION_LISTING_DELETED,
            "listing",
            str(listing_id) if listing_id else None,
            {"title": title, "applications_cascaded": applications_cascaded, "appointments_unlinked": appointments_unlinked},
            actor=actor,
            device=device,
        )

    # Cover image ng listing.
    def cover_uploaded(self, actor: User = None, listing_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_COVER_UPLOADED, "listing", str(listing_id) if listing_id else None, actor=actor, device=device)

    # Tinanggal yung cover image ng listing.
    def cover_removed(self, actor: User = None, listing_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_COVER_REMOVED, "listing", str(listing_id) if listing_id else None, actor=actor, device=device)


    # Saved listing template na ginawa ng student.
    def template_created(self, actor: User = None, template_id: int = None, name: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_TEMPLATE_CREATED, "listing_template", str(template_id) if template_id else None, {"name": name}, actor=actor, device=device)

    # Saved template na binura.
    def template_deleted(self, actor: User = None, template_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_TEMPLATE_DELETED, "listing_template", str(template_id) if template_id else None, actor=actor, device=device)


    # Patient nag-apply sa isang listing.
    def application_created(self, actor: User = None, application_id: int = None, listing_id: int = None, listing_title: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPLICATION_CREATED, "application", str(application_id) if application_id else None, {"listing_id": listing_id, "listing_title": listing_title}, actor=actor, device=device)

    # Accept o reject yung application.
    def application_decision(self, actor: User = None, application_id: int = None, decision: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPLICATION_DECISION, "application", str(application_id) if application_id else None, {"status": decision}, actor=actor, device=device)

    # Patient nag-withdraw ng application.
    def application_withdrawn(self, actor: User = None, application_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPLICATION_WITHDRAWN, "application", str(application_id) if application_id else None, actor=actor, device=device)


    # Bagong request, kasama yung listing at oras.
    def appointment_requested(self, actor: User = None, appointment_id: int = None, listing_id: int = None, listing_title: str = None, starts_at: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_REQUESTED, "appointment", str(appointment_id) if appointment_id else None, {"listing_id": listing_id, "listing_title": listing_title, "starts_at": starts_at}, actor=actor, device=device)

    # Kinansela yung appointment, student o patient man.
    def appointment_cancelled(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_CANCELLED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    # Patient humingi ng bagong oras.
    def appointment_rescheduled(self, actor: User = None, appointment_id: int = None, proposed_at: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_RESCHEDULED, "appointment", str(appointment_id) if appointment_id else None, {"proposed_at": proposed_at}, actor=actor, device=device)

    # Student nag-propose ng ibang oras.
    def appointment_proposed(self, actor: User = None, appointment_id: int = None, proposed_at: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_PROPOSED, "appointment", str(appointment_id) if appointment_id else None, {"proposed_at": proposed_at}, actor=actor, device=device)

    # Confirm na yung slot.
    def appointment_confirmed(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_CONFIRMED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    # Tinanggihan yung request.
    def appointment_rejected(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_REJECTED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    # Tapos na yung appointment.
    def appointment_completed(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_COMPLETED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)

    # Hard delete ng appointment. Hindi na ito maibabalik.
    def appointment_deleted(self, actor: User = None, appointment_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(self.ACTION_APPOINTMENT_DELETED, "appointment", str(appointment_id) if appointment_id else None, actor=actor, device=device)


    # Admin nag-approve ng student galing sa users page.
    def admin_user_approved(self, admin: User = None, actor: User = None, student_user: User = None, target_user: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
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

    # Galing sa approval queue. Ibang action name para madaling
    # i-filter sa audit kung saan galing yung approve.
    def student_approved(self, actor: User = None, student: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(
            self.ACTION_STUDENT_APPROVED,
            "user",
            str(student.id) if student else None,
            {"student_email": student.email[:255] if student else None, "approval_status": "approved"},
            actor=actor,
            device=device,
        )

    # Student na hinarangan ng admin.
    def student_rejected(self, actor: User = None, student: User = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(
            self.ACTION_STUDENT_REJECTED,
            "user",
            str(student.id) if student else None,
            {"student_email": student.email[:255] if student else None},
            actor=actor,
            device=device,
        )

    # Bura ng account. Kasama yung role at email snapshot.
    def admin_user_deleted(self, admin: User = None, actor: User = None, target_user: User = None, role: str = None, email: str = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_USER_DELETED,
            "user",
            str(target_user.id) if target_user else None,
            {"role": role, "email": email[:255] if email else (target_user.email[:255] if target_user else None)},
            actor=a,
            device=device,
        )

    # Admin ang nagbura ng listing, hindi yung owner.
    def admin_listing_deleted(self, admin: User = None, actor: User = None, listing_id: int = None, title: str = None, applications_cascaded: int = 0, appointments_unlinked: int = 0, device: DeviceInfo = None, **kwargs) -> AuditLog:
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_LISTING_DELETED,
            "listing",
            str(listing_id) if listing_id else None,
            {"title": title, "applications_cascaded": applications_cascaded, "appointments_unlinked": appointments_unlinked},
            actor=a,
            device=device,
        )

    # Admin nagbura ng appointment record.
    def admin_appointment_deleted(self, admin: User = None, actor: User = None, appointment_id: int = None, listing_id: Optional[int] = None, patient_id: int = None, student_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_APPOINTMENT_DELETED,
            "appointment",
            str(appointment_id) if appointment_id else None,
            {"listing_id": listing_id, "patient_id": patient_id, "student_id": student_id},
            actor=a,
            device=device,
        )

    # Admin nagsara ng listing mula sa oversight view.
    def admin_listing_closed(self, admin: User = None, actor: User = None, listing_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_LISTING_CLOSED,
            "listing",
            str(listing_id) if listing_id else None,
            {"status": "closed"},
            actor=a,
            device=device,
        )

    # Activate o deactivate ng account.
    def admin_user_toggle(self, admin: User = None, actor: User = None, target_user: User = None, is_active: bool = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        a = admin or actor
        return self._add_log(
            self.ACTION_ADMIN_USER_TOGGLE,
            "user",
            str(target_user.id) if target_user else None,
            {"is_active": is_active, "target_email": target_user.email[:255] if target_user else None},
            actor=a,
            device=device,
        )

    # Namarkahan na read yung notification.
    def notification_read(self, actor: User = None, notification_id: int = None, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(
            self.ACTION_NOTIFICATION_READ,
            "notification",
            str(notification_id) if notification_id else None,
            actor=actor,
            device=device,
        )


    # Naka-log kahit denied, para may record kung may
    # nagtatangka tumingin ng profile na hindi puwede.
    def profile_viewed(self, viewer: User = None, target_user: User = None, allowed: bool = True, device: DeviceInfo = None, **kwargs) -> AuditLog:
        return self._add_log(
            self.ACTION_PROFILE_VIEWED,
            "user",
            str(target_user.id) if target_user else None,
            {"viewer_id": viewer.id if viewer else None, "viewer_role": viewer.role if viewer else None, "target_role": target_user.role if target_user else None, "allowed": allowed},
            actor=viewer,
            device=device,
        )


# Isang instance lang ito, ginagamit ng lahat ng routes.
audit_logger = AuditLogger()


# Shortcut para sa routes: kunin yung DeviceInfo sa request.
def get_device_info(request_obj=None) -> DeviceInfo:
    return DeviceInfo.from_request(request_obj)

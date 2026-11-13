# Flow ng student approval sa isang lugar lang. Kung nasa
# routes, nakakalimutan yung audit, notify, at email.
from .audit import audit_logger
from .extensions import db
from .models import User
from .services import notify, send_email


# Pag verified na yung email, pending pa rin hanggang
# i-approve ng admin. Patients at admin, hindi naka-gate.
class StudentApprovalService:

    PENDING = "pending"
    APPROVED = "approved"
    VALID_STATUSES = {PENDING, APPROVED}

    # Tinatawag sa registration, bago pa ma-verify yung OTP.
    @classmethod
    def mark_pending(cls, student):
        if student.role != "student":
            return
        student.require_admin_approval()
        db.session.add(student)

    # Notify admins kapag na-verify na yung email at pending pa.
    @classmethod
    def email_verified(cls, student):
        if student.role == "student" and student.approval_status == cls.PENDING:
            cls._notify_admins(student)

    # Lahat ng active admin mabibigyan ng in-app notification.
    @classmethod
    def _notify_admins(cls, student):
        admins = db.session.scalars(
            db.select(User).where(User.role == "admin", User.is_active.is_(True))
        ).all()
        for admin in admins:
            notify(admin, f"New student awaiting approval: {student.full_name}.")

    # Query para sa approval queue: verified, active, pending.
    @classmethod
    def pending_students(cls):
        return db.select(User).where(
            User.role == "student",
            User.approval_status == cls.PENDING,
            User.email_verified.is_(True),
            User.is_active.is_(True),
        )

    # Student lang na pending at verified ang puwedeng i-approve.
    # May ValueError kaya hindi basta nababago yung status.
    @classmethod
    def approve(cls, student, admin):
        if student.role != "student" or student.approval_status != cls.PENDING or not student.email_verified:
            raise ValueError("That account is not a pending student.")
        student.approve()
        audit_logger.student_approved(actor=admin, student=student)
        notify(student, "Your account has been approved. You can now sign in.")
        db.session.commit()
        send_email(
            student.email,
            "Your NU DentalConnect account was approved",
            "notice",
            user=student,
            message="Your student account has been approved. You can now sign in and publish appointment listings.",
        )

    # Reject = deactivate, hindi delete, para may record pa rin.
    @classmethod
    def reject(cls, student, admin):
        if student.role != "student" or student.approval_status != cls.PENDING:
            raise ValueError("That account is not a pending student.")
        student.deactivate()
        audit_logger.student_rejected(actor=admin, student=student)
        notify(student, "Your registration was not approved. Please contact the administration office.")
        db.session.commit()
        send_email(
            student.email,
            "Your NU DentalConnect registration was not approved",
            "notice",
            user=student,
            message="Your student registration was not approved. Please contact the administration office if you believe this is an error.",
        )

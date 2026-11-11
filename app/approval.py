"""Student approval lifecycle.

A verified student account stays locked until an administrator approves it.
Keeping the rule in one service means routes cannot forget the audit row,
the in-app notification, or the "patients are never gated" rule.
"""
from .audit import audit_logger
from .extensions import db
from .models import User
from .services import notify, send_email


class StudentApprovalService:
    """Single home for the pending-student workflow."""

    PENDING = "pending"
    APPROVED = "approved"
    VALID_STATUSES = {PENDING, APPROVED}

    @classmethod
    def mark_pending(cls, student):
        """Called at student registration, before the OTP is verified."""
        if student.role != "student":
            return
        student.require_admin_approval()
        db.session.add(student)

    @classmethod
    def email_verified(cls, student):
        """Notify admins only once a student has completed email verification."""
        if student.role == "student" and student.approval_status == cls.PENDING:
            cls._notify_admins(student)

    @classmethod
    def _notify_admins(cls, student):
        """In-app notification for every active administrator."""
        admins = db.session.scalars(
            db.select(User).where(User.role == "admin", User.is_active.is_(True))
        ).all()
        for admin in admins:
            notify(admin, f"New student awaiting approval: {student.full_name}.")

    @classmethod
    def pending_students(cls):
        return db.select(User).where(
            User.role == "student",
            User.approval_status == cls.PENDING,
            User.email_verified.is_(True),
            User.is_active.is_(True),
        )

    @classmethod
    def approve(cls, student, admin):
        """Approve a pending student and tell them by in-app notice and email."""
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

    @classmethod
    def reject(cls, student, admin):
        """Deactivate a pending student without deleting their record."""
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

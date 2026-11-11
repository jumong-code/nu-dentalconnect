"""
Profile access control policy for NU DentalConnect.

Centralizes all profile visibility rules in one place for auditability and testability.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional

from .models import Appointment, Patient, PatientApplication, RecruitmentListing, User


class AccessResult(Enum):
    """Result of a profile access check."""
    ALLOWED = "allowed"
    DENIED = "denied"
    NOT_FOUND = "not_found"  # For patient enumeration protection


class ProfileAccessPolicy:
    """
    Encapsulates all profile viewing authorization logic.

    Rules:
    - Authenticated patients can view active, verified, admin-approved students
    - Students can view patients ONLY if patient has contacted them (application or appointment)
    - Admins can view all profiles
    - Anonymous users and student-to-student views are denied
    - Unauthorized patient access returns NOT_FOUND (404) to prevent enumeration
    - Access revoked when patient withdraws/cancels contact
    """

    # Fields visible to a contacted student viewing a patient profile
    PATIENT_VISIBLE_FIELDS = [
        "full_name",
        "avatar_image",
        "phone",
        "email",
        "application_message",
    ]

    # Fields visible on a student's public profile
    STUDENT_PUBLIC_FIELDS = [
        "full_name",
        "avatar_image",
        "year_level",
        "campus",
        "bio",
        "facebook_url",
        "published_listings",
    ]

    @classmethod
    def can_view_student_profile(cls, viewer: User, target_student: User) -> AccessResult:
        """
        Check if viewer can see a student's profile.

        Patients: can view if student is active, verified, AND admin-approved
        Admins: can always view
        Students/Anonymous: denied
        """
        if not viewer.is_authenticated:
            return AccessResult.DENIED

        if viewer.role == "admin":
            return AccessResult.ALLOWED

        if viewer.role == "patient":
            # Student must be active, email verified, and admin-approved
            if target_student.is_active and target_student.email_verified and target_student.is_approved():
                return AccessResult.ALLOWED
            return AccessResult.NOT_FOUND  # Hide unapproved students

        # Student-to-student and other roles: denied
        return AccessResult.DENIED

    @classmethod
    def can_view_patient_profile(cls, viewer: User, target_patient: User) -> AccessResult:
        """
        Check if viewer can see a patient's profile.

        Admins: can always view
        Students: only if patient has contacted them (application or appointment)
        Patients/Anonymous: denied (patients can't view other patients)
        """
        if not viewer.is_authenticated:
            return AccessResult.DENIED

        if viewer.role == "admin":
            return AccessResult.ALLOWED

        if viewer.role == "student":
            if not viewer.student_profile or not target_patient.patient_profile:
                return AccessResult.DENIED

            student_id = viewer.student_profile.id

            # Check if patient has an application to one of this student's listings
            has_application = PatientApplication.query.join(RecruitmentListing).filter(
                PatientApplication.patient_id == target_patient.patient_profile.id,
                RecruitmentListing.student_id == student_id,
                PatientApplication.status.in_(["pending", "accepted"])  # Only active applications
            ).first() is not None

            if has_application:
                return AccessResult.ALLOWED

            # Check if patient has an appointment with this student
            has_appointment = Appointment.query.filter(
                Appointment.patient_id == target_patient.patient_profile.id,
                Appointment.student_id == student_id,
                Appointment.status.in_(["pending", "confirmed", "reschedule_requested", "completed"])
            ).first() is not None

            if has_appointment:
                return AccessResult.ALLOWED

            # No contact relationship - return NOT_FOUND to prevent enumeration
            return AccessResult.NOT_FOUND

        # Patient-to-patient views also return NOT_FOUND so patient IDs cannot be
        # enumerated by comparing 403 and 404 responses.
        return AccessResult.NOT_FOUND

    @classmethod
    def can_view_profile(cls, viewer: User, target_user: User) -> AccessResult:
        """
        Main entry point: check if viewer can view target_user's profile.

        Routes to appropriate check based on target user's role.
        """
        if target_user.role == "student":
            return cls.can_view_student_profile(viewer, target_user)
        elif target_user.role == "patient":
            return cls.can_view_patient_profile(viewer, target_user)
        elif target_user.role == "admin":
            # Admins can only be viewed by other admins
            return AccessResult.ALLOWED if viewer.is_authenticated and viewer.role == "admin" else AccessResult.DENIED
        return AccessResult.DENIED

    @classmethod
    def get_visible_patient_fields(cls, viewer: User, target_patient: User) -> dict:
        """
        Return the subset of patient fields visible to the viewer.

        Only called after can_view_patient_profile returns ALLOWED.
        """
        result = {}
        patient_profile = target_patient.patient_profile

        if "full_name" in cls.PATIENT_VISIBLE_FIELDS:
            result["full_name"] = target_patient.full_name
        if "avatar_image" in cls.PATIENT_VISIBLE_FIELDS:
            result["avatar_image"] = patient_profile.avatar_image if patient_profile else None
        if "phone" in cls.PATIENT_VISIBLE_FIELDS:
            result["phone"] = target_patient.phone
        if "email" in cls.PATIENT_VISIBLE_FIELDS:
            result["email"] = target_patient.email
        if "application_message" in cls.PATIENT_VISIBLE_FIELDS:
            application = None
            if patient_profile:
                application = PatientApplication.query.join(RecruitmentListing).filter(
                    PatientApplication.patient_id == patient_profile.id,
                    PatientApplication.status.in_(["pending", "accepted"]),
                ).order_by(PatientApplication.created_at.desc()).first()
            result["application_message"] = application.message if application else None

        return result

    @classmethod
    def get_visible_student_fields(cls, viewer: User, target_student: User) -> dict:
        """
        Return the subset of student fields visible to the viewer.

        Only called after can_view_student_profile returns ALLOWED.
        """
        result = {}
        student_profile = target_student.student_profile

        if "full_name" in cls.STUDENT_PUBLIC_FIELDS:
            result["full_name"] = target_student.full_name
        if "avatar_image" in cls.STUDENT_PUBLIC_FIELDS:
            result["avatar_image"] = student_profile.avatar_image if student_profile else None
        if "year_level" in cls.STUDENT_PUBLIC_FIELDS:
            result["year_level"] = student_profile.year_level if student_profile else None
        if "campus" in cls.STUDENT_PUBLIC_FIELDS:
            result["campus"] = student_profile.campus if student_profile else None
        if "bio" in cls.STUDENT_PUBLIC_FIELDS:
            result["bio"] = student_profile.bio if student_profile else None
        if "facebook_url" in cls.STUDENT_PUBLIC_FIELDS:
            result["facebook_url"] = student_profile.facebook_url if student_profile else None
        if "published_listings" in cls.STUDENT_PUBLIC_FIELDS:
            if student_profile:
                result["published_listings"] = RecruitmentListing.query.filter_by(
                    student_id=student_profile.id, status="published"
                ).order_by(RecruitmentListing.created_at.desc()).all()
            else:
                result["published_listings"] = []

        return result

    @classmethod
    def check_contact_revoked(cls, patient_user: User, student_user: User) -> bool:
        """
        Check if patient's contact with student has been revoked.

        Returns True if access should be revoked (patient withdrew/cancelled).
        Called when a student tries to view a patient profile.
        """
        if not patient_user.patient_profile or not student_user.student_profile:
            return True

        patient_id = patient_user.patient_profile.id
        student_id = student_user.student_profile.id

        # Check for active applications
        active_application = PatientApplication.query.join(RecruitmentListing).filter(
            PatientApplication.patient_id == patient_id,
            RecruitmentListing.student_id == student_id,
            PatientApplication.status.in_(["pending", "accepted"])
        ).first()

        if active_application:
            return False  # Contact still active

        # Check for active appointments
        active_appointment = Appointment.query.filter(
            Appointment.patient_id == patient_id,
            Appointment.student_id == student_id,
            Appointment.status.in_(["pending", "confirmed", "reschedule_requested", "completed"])
        ).first()

        if active_appointment:
            return False  # Contact still active

        # No active contact - access revoked
        return True
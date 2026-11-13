# Rules kung sino ang puwedeng tumingin ng profile. Nasa
# isang class para isang lugar lang ang pagbabago.
from __future__ import annotations
from enum import Enum
from typing import Optional

from .models import Appointment, Patient, PatientApplication, RecruitmentListing, User


# Tatlong sagot: allowed, denied, at not_found. Yung
# not_found ang gamit para hindi mabisto yung existence.
class AccessResult(Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    NOT_FOUND = "not_found"


# Policies dito (OOP style). Patients puwedeng tumingin ng
# student; students sa patient na may contact lang; admin sa lahat.
class ProfileAccessPolicy:

    # Fields na pwede kong ipakita sa student na may contact.
    PATIENT_VISIBLE_FIELDS = [
        "full_name",
        "avatar_image",
        "phone",
        "email",
        "application_message",
    ]

    # Fields na nakikita ng patient sa student profile.
    STUDENT_PUBLIC_FIELDS = [
        "full_name",
        "avatar_image",
        "year_level",
        "campus",
        "bio",
        "facebook_url",
        "published_listings",
    ]

    # Patient puwede lang kung active, verified, at approved
    # yung student. Yung iba, denied.
    @classmethod
    def can_view_student_profile(cls, viewer: User, target_student: User) -> AccessResult:
        if not viewer.is_authenticated:
            return AccessResult.DENIED

        if viewer.role == "admin":
            return AccessResult.ALLOWED

        # Pag hindi approved yung student, NOT_FOUND ang sagot,
        # hindi DENIED, para mukhang wala talaga yung profile.
        if viewer.role == "patient":
            if target_student.is_active and target_student.email_verified and target_student.is_approved():
                return AccessResult.ALLOWED
            return AccessResult.NOT_FOUND

        return AccessResult.DENIED

    # Students lang ang may extra rule: kailangan may contact,
    # kundi NOT_FOUND para hindi ma-enumerate yung patient IDs.
    @classmethod
    def can_view_patient_profile(cls, viewer: User, target_patient: User) -> AccessResult:
        if not viewer.is_authenticated:
            return AccessResult.DENIED

        if viewer.role == "admin":
            return AccessResult.ALLOWED

        if viewer.role == "student":
            if not viewer.student_profile or not target_patient.patient_profile:
                return AccessResult.DENIED

            student_id = viewer.student_profile.id

            # Pending at accepted lang ang counted. Pag withdrawn o
            # rejected, wala nang access.
            has_application = PatientApplication.query.join(RecruitmentListing).filter(
                PatientApplication.patient_id == target_patient.patient_profile.id,
                RecruitmentListing.student_id == student_id,
                PatientApplication.status.in_(["pending", "accepted"])
            ).first() is not None

            if has_application:
                return AccessResult.ALLOWED

            # Kung may appointment sa student na ito, may access na,
            # kahit hindi sa application galing.
            has_appointment = Appointment.query.filter(
                Appointment.patient_id == target_patient.patient_profile.id,
                Appointment.student_id == student_id,
                Appointment.status.in_(["pending", "confirmed", "reschedule_requested", "completed"])
            ).first() is not None

            if has_appointment:
                return AccessResult.ALLOWED

            return AccessResult.NOT_FOUND

        return AccessResult.NOT_FOUND

    # Entry point ng route. Ibabase sa role ng target kung
    # aling check ang tatawagin.
    @classmethod
    def can_view_profile(cls, viewer: User, target_user: User) -> AccessResult:
        if target_user.role == "student":
            return cls.can_view_student_profile(viewer, target_user)
        elif target_user.role == "patient":
            return cls.can_view_patient_profile(viewer, target_user)
        elif target_user.role == "admin":
            return AccessResult.ALLOWED if viewer.is_authenticated and viewer.role == "admin" else AccessResult.DENIED
        return AccessResult.DENIED

    # Kada field, may check bago ilagay para madaling alisin
    # kung babaguhin yung policy.
    @classmethod
    def get_visible_patient_fields(cls, viewer: User, target_patient: User) -> dict:
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

    # Dito lang published listings ang isinasama.
    @classmethod
    def get_visible_student_fields(cls, viewer: User, target_student: User) -> dict:
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

    # True ibig sabihin revoked na. Tinitingnan ko yung active
    # application at appointment bago sabihing wala nang access.
    @classmethod
    def check_contact_revoked(cls, patient_user: User, student_user: User) -> bool:
        if not patient_user.patient_profile or not student_user.student_profile:
            return True

        patient_id = patient_user.patient_profile.id
        student_id = student_user.student_profile.id

        active_application = PatientApplication.query.join(RecruitmentListing).filter(
            PatientApplication.patient_id == patient_id,
            RecruitmentListing.student_id == student_id,
            PatientApplication.status.in_(["pending", "accepted"])
        ).first()

        if active_application:
            return False

        active_appointment = Appointment.query.filter(
            Appointment.patient_id == patient_id,
            Appointment.student_id == student_id,
            Appointment.status.in_(["pending", "confirmed", "reschedule_requested", "completed"])
        ).first()

        if active_appointment:
            return False

        return True
# Dito naka-define lahat ng table. Isa-isa ko ginawa yung class
# para malinaw kung saan nakaimbak yung data ng app.
from datetime import datetime, timezone
from sqlalchemy import Index
from itsdangerous import URLSafeTimedSerializer
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from .extensions import db, login_manager


# Helper sa oras. UTC ang sinasave ko sa database, tapos
# tinatanggal ko yung tzinfo para plain DateTime ang column.
def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Class ng User. Nandito na yung password at approval methods
# para hindi nagkakalat sa routes (encapsulation).
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("patient", "student", "admin", name="user_role"), nullable=False)
    phone = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    # VARCHAR ito hindi ENUM para madaling magdagdag ng status.
    # Default pending; patients at admin hindi naman hinihintay.
    approval_status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    patient_profile = db.relationship("Patient", back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    student_profile = db.relationship("DentistryStudent", back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    notifications = db.relationship("Notification", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

    # Students lang ang naka-gate sa admin approval.
    # Patients at admin, laging true.
    def is_approved(self) -> bool:
        if self.role == "student":
            return self.approval_status == "approved"
        return True

    # Tinatawag pag nag-register ang student. Pending muna siya
    # kahit ma-verify pa yung email.
    def require_admin_approval(self):
        if self.role != "student":
            raise ValueError("Only student accounts require approval.")
        self.approval_status = "pending"

    # Dito yung totoong approval. Student lang puwede, kaya may
    # check bago baguhin yung status.
    def approve(self):
        if self.role != "student":
            raise ValueError("Only student accounts can be approved.")
        self.approval_status = "approved"

    # Deactivate hindi delete, para may record pa rin. Tapos
    # tinaasan ko auth_version para mawala agad yung session.
    def deactivate(self):
        self.is_active = False
        self.auth_version += 1

    # Hash muna bago i-save. Di ko dapat i-store yung plain password.
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # Kinukumpara yung tinype na password sa hash, hindi sa plain text.
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Isinasama ko yung auth_version sa session id. Pag nagbago
    # yung version, expired na agad yung lumang session.
    def get_id(self):
        return f"{self.id}:{self.auth_version}"

    # Signed token para sa reset link. Nakalakip yung email at
    # may salt para hindi magamit sa ibang purpose.
    def get_reset_token(self):
        return URLSafeTimedSerializer(current_app.config["SECRET_KEY"]).dumps(self.email, salt="password-reset")

    # Pag sira, expired, o sobra na sa max_age yung token, None
    # ang sagot. Hindi ko pinapakita kung bakit sira.
    @staticmethod
    def verify_reset_token(token, max_age=1800):
        try:
            email = URLSafeTimedSerializer(current_app.config["SECRET_KEY"]).loads(token, salt="password-reset", max_age=max_age)
        except Exception:
            return None
        return db.session.scalar(db.select(User).where(User.email == email))


# Patient profile. Yung shared fields tulad ng name at email
# nasa User, dito lang yung avatar.
class Patient(db.Model):
    __tablename__ = "patients"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    avatar_image = db.Column(db.String(255), nullable=True)
    user = db.relationship("User", back_populates="patient_profile")


# Student profile. Dito yung year level, campus, at bio na
# hindi kailangan ng patient.
class DentistryStudent(db.Model):
    __tablename__ = "dentistry_students"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    year_level = db.Column(db.String(80))
    bio = db.Column(db.String(500))
    campus = db.Column(db.String(120))
    facebook_url = db.Column(db.String(255))
    avatar_image = db.Column(db.String(255), nullable=True)
    user = db.relationship("User", back_populates="student_profile")
    listings = db.relationship("RecruitmentListing", back_populates="student", cascade="all, delete-orphan", passive_deletes=True)


# Listing na pinopost ng student. draft, published, closed
# ang status; yung submission_key pang-iwas sa double submit.
class RecruitmentListing(db.Model):
    __tablename__ = "recruitment_listings"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.ForeignKey("dentistry_students.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False, index=True)
    location = db.Column(db.String(180), nullable=False)
    preferred_schedule = db.Column(db.String(180), nullable=False)
    eligibility = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum("draft", "published", "closed", name="listing_status"), nullable=False, default="draft", index=True)
    submission_key = db.Column(db.String(64), unique=True)
    cover_image = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    student = db.relationship("DentistryStudent", back_populates="listings")
    applications = db.relationship("PatientApplication", back_populates="listing", cascade="all, delete-orphan", passive_deletes=True)


# Saved template ng student para hindi na ulitin yung fields
# tuwing gagawa ng bagong listing.
class StudentListingTemplate(db.Model):
    __tablename__ = "student_listing_templates"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.ForeignKey("dentistry_students.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(180), nullable=False)
    preferred_schedule = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    eligibility = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    student = db.relationship("DentistryStudent")


# Application ng patient sa isang listing. Hindi ito booking.
class PatientApplication(db.Model):
    __tablename__ = "patient_applications"
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.ForeignKey("recruitment_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = db.Column(db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    message = db.Column(db.Text)
    status = db.Column(db.Enum("pending", "accepted", "rejected", "withdrawn", name="application_status"), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    listing = db.relationship("RecruitmentListing", back_populates="applications")
    patient = db.relationship("Patient")
    # Isang application lang per patient per listing. Pag naulit,
    # IntegrityError sa route, tapos sasabihin ko na may existing na.
    __table_args__ = (db.UniqueConstraint("listing_id", "patient_id", name="uq_application_patient_listing"),)


# Appointment record. Isang patient at isang student per row.
# UTC lahat ng oras dito, Manila time lang sa display.
class Appointment(db.Model):
    __tablename__ = "appointments"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.ForeignKey("dentistry_students.id", ondelete="CASCADE"), nullable=False, index=True)
    listing_id = db.Column(db.ForeignKey("recruitment_listings.id", ondelete="SET NULL"))
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    location = db.Column(db.String(180), nullable=False)
    note = db.Column(db.String(1000))
    status = db.Column(db.Enum("pending", "confirmed", "reschedule_requested", "completed", "cancelled", "rejected", name="appointment_status"), nullable=False, default="pending", index=True)
    proposed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    patient = db.relationship("Patient")
    student = db.relationship("DentistryStudent")
    listing = db.relationship("RecruitmentListing")

    # Puwede pa i-cancel kung hindi pa tapos at wala pang
    # nakalipas na oras yung appointment.
    def can_cancel(self):
        return self.status in {"pending", "confirmed", "reschedule_requested"} and self.starts_at > utcnow()


# Simpleng in-app notification. read_at lang ang nagsasabi
# kung nabasa na.
class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime)
    user = db.relationship("User", back_populates="notifications")


# OTP challenge para sa email verification. Naka-hash yung
# code, may expiry, consumed_at, at bilang ng attempts.
class OTPVerification(db.Model):
    __tablename__ = "otp_verifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_digest = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    consumed_at = db.Column(db.DateTime)
    attempts = db.Column(db.SmallInteger, nullable=False, default=0)
    user = db.relationship("User", backref=db.backref("otp_verifications", cascade="all, delete-orphan", passive_deletes=True))

    __table_args__ = (Index("ix_otp_user_created", "user_id", "created_at"),)


# Audit trail. Bawat action may actor, IP, device details, at
# JSON na details. Wala dapat password o OTP dito.
class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_email = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(80))
    details = db.Column(db.JSON, nullable=False, default=dict)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    __table_args__ = (Index("ix_audit_logs_created_id", "created_at", "id"),)

    # Hindi ako nag-iimbak ng object, ID lang. Kukunin ko na lang
    # dito pag kailangan, at None kung na-delete na yung user.
    @property
    def actor(self):
        return db.session.get(User, self.actor_user_id) if self.actor_user_id else None


# Bawat request, dito kinukuha ni Flask-Login yung user.
# Dito rin naka-check kung active, verified, approved, at
# tugma pa yung auth_version.
@login_manager.user_loader
def load_user(user_id):
    try:
        user_id_value, version_value = user_id.split(":", 1)
        expected_version = int(version_value)
        user = db.session.get(User, int(user_id_value))
    except (AttributeError, ValueError):
        return None
    return user if user and user.is_active and user.email_verified and user.is_approved() and user.auth_version == expected_version else None


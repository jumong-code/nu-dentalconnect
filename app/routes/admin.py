from datetime import datetime, timedelta, timezone
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload
from ..approval import StudentApprovalService
from ..audit import audit_logger, get_device_info
from ..extensions import db
from ..forms import AdminSetPasswordForm
from ..models import Appointment, AuditLog, DentistryStudent, Patient, PatientApplication, RecruitmentListing, User, utcnow
from ..services import notify, send_email
from ..upload import get_upload_root
from ..time_utils import MANILA_TZ

bp = Blueprint("admin", __name__)


def admin_required():
    if current_user.role != "admin":
        abort(403)


@bp.route("/users")
@login_required
def users():
    admin_required()
    query = User.query
    search = request.args.get("q", "").strip()[:100]
    role = request.args.get("role", "").strip()
    if search:
        query = query.filter(db.or_(User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")))
    if role in {"patient", "student", "admin"}:
        query = query.filter_by(role=role)
    users_page = query.order_by(User.created_at.desc(), User.id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, max_per_page=20, error_out=False
    )
    return render_template("admin/users.html", users=users_page)


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    admin_required()
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own administrator account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    user.auth_version += 1  # Existing sessions stop resolving immediately.
    audit_logger.admin_user_toggle(actor=current_user, target_user=user, is_active=user.is_active)
    db.session.commit()
    flash("Account status updated.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/set-password", methods=["GET", "POST"])
@login_required
def set_user_password(user_id):
    """Admin sets a password for a non-admin user. Never used for administrators."""
    admin_required()
    user = db.get_or_404(User, user_id)
    if user.role == "admin":
        flash("Cannot set a password for administrator accounts.", "error")
        return redirect(url_for("admin.users"))

    form = AdminSetPasswordForm()
    if form.validate_on_submit():
        device = get_device_info(request)
        user.set_password(form.password.data)
        user.auth_version += 1  # Invalidate every existing session.
        audit_logger.password_admin_set(actor=current_user, target_user=user, device=device)
        db.session.commit()
        # The email never contains the new password.
        send_email(
            user.email,
            "Your NU DentalConnect password was changed",
            "notice",
            user=user,
            message="An administrator set a new password for your account. If you did not request this, contact the administration office immediately.",
        )
        flash("Password has been set. The user's existing sessions have been invalidated and they were notified by email.", "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/set_password.html", form=form, target_user=user)


@bp.route("/students/pending")
@login_required
def pending_students():
    admin_required()
    students_page = db.paginate(
        StudentApprovalService.pending_students().order_by(User.created_at.asc()),
        page=request.args.get("page", 1, type=int),
        per_page=20,
        max_per_page=20,
        error_out=False,
    )
    return render_template("admin/pending_students.html", students=students_page)


@bp.route("/students/<int:user_id>/approve", methods=["POST"])
@login_required
def approve_student(user_id):
    admin_required()
    student = db.get_or_404(User, user_id)
    try:
        StudentApprovalService.approve(student, current_user)
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Student approved and notified.", "success")
    return redirect(url_for("admin.pending_students"))


@bp.route("/students/<int:user_id>/reject", methods=["POST"])
@login_required
def reject_student(user_id):
    admin_required()
    student = db.get_or_404(User, user_id)
    try:
        StudentApprovalService.reject(student, current_user)
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Student registration rejected and the account deactivated.", "success")
    return redirect(url_for("admin.pending_students"))


@bp.route("/listings")
@login_required
def listings():
    admin_required()
    listings_page = RecruitmentListing.query.options(
        joinedload(RecruitmentListing.student).joinedload(DentistryStudent.user)
    ).order_by(RecruitmentListing.created_at.desc(), RecruitmentListing.id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, max_per_page=20, error_out=False
    )
    return render_template("admin/listings.html", listings=listings_page)


@bp.route("/listings/<int:listing_id>/close", methods=["POST"])
@login_required
def close_listing(listing_id):
    admin_required()
    listing = db.get_or_404(RecruitmentListing, listing_id)
    listing.status = "closed"
    audit_logger.admin_listing_closed(actor=current_user, listing_id=listing.id)
    db.session.commit()
    flash("Listing closed.", "success")
    return redirect(url_for("admin.listings"))


@bp.route("/appointments")
@login_required
def appointments():
    admin_required()
    appointments_page = Appointment.query.options(
        joinedload(Appointment.patient).joinedload(Patient.user),
        joinedload(Appointment.student).joinedload(DentistryStudent.user),
        joinedload(Appointment.listing),
    ).order_by(Appointment.starts_at.desc(), Appointment.id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=25, max_per_page=25, error_out=False
    )
    return render_template("admin/appointments.html", appointments=appointments_page)


@bp.route("/audit")
@login_required
def audit():
    """Audit history with action, actor and date-range filters.

    Sorting is always ``created_at DESC, id DESC`` so two events in the same
    second keep a stable, newest-first order.
    """
    admin_required()
    action = request.args.get("action", "").strip()[:80]
    actor = request.args.get("actor", "").strip()[:255]
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor_email.ilike(f"%{actor}%"))
    try:
        if date_from:
            start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(AuditLog.created_at >= start)
        if date_to:
            end = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(AuditLog.created_at < end)
    except ValueError:
        flash("Use a valid date in the date filters.", "error")

    logs = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=50, max_per_page=50, error_out=False
    )
    actions = db.session.scalars(
        db.select(AuditLog.action).distinct().order_by(AuditLog.action)
    ).all()
    return render_template("admin/audit.html", logs=logs, actions=actions)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    """Hard delete a user account. Requires the typed email as confirmation."""
    admin_required()
    user = db.get_or_404(User, user_id)

    if user.id == current_user.id:
        flash("You cannot delete your own administrator account.", "error")
        return redirect(url_for("admin.users"))

    if user.role == "admin":
        active_admin_count = db.session.scalar(
            db.select(db.func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
        )
        if active_admin_count <= 1:
            flash("Cannot delete the last active administrator.", "error")
            return redirect(url_for("admin.users"))

    profile = user.patient_profile if user.role == "patient" else user.student_profile
    if profile is not None:
        future_confirmed = db.session.scalar(
            db.select(db.func.count(Appointment.id)).where(
                (Appointment.patient_id == profile.id) if user.role == "patient" else (Appointment.student_id == profile.id),
                Appointment.status == "confirmed",
                Appointment.starts_at > utcnow(),
            )
        )
        if future_confirmed:
            flash(f"Cannot delete: user has {future_confirmed} confirmed future appointment(s). Cancel them first.", "error")
            return redirect(url_for("admin.users"))

    confirm_email = request.form.get("confirm_email", "").strip()
    if len(confirm_email) > 255 or confirm_email.lower() != user.email:
        flash("Email confirmation does not match. Deletion cancelled.", "error")
        return redirect(url_for("admin.users"))

    avatar_filename = profile.avatar_image if profile is not None else None
    audit_logger.admin_user_deleted(actor=current_user, target_user=user, role=user.role)
    db.session.delete(user)
    db.session.commit()

    if avatar_filename:
        try:
            filepath = get_upload_root() / "avatars" / avatar_filename
            if filepath.exists():
                filepath.unlink()
        except Exception:
            current_app.logger.warning("Failed to delete avatar file: %s", avatar_filename)

    flash("User account deleted.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/listings/<int:listing_id>/delete", methods=["POST"])
@login_required
def delete_listing(listing_id):
    """Hard delete a listing, confirming first when future appointments exist."""
    admin_required()
    listing = db.get_or_404(RecruitmentListing, listing_id)

    future_confirmed = 0
    if listing.status != "closed":
        future_confirmed = db.session.scalar(
            db.select(db.func.count(Appointment.id)).where(
                Appointment.listing_id == listing.id,
                Appointment.status == "confirmed",
                Appointment.starts_at > utcnow(),
            )
        )

    if future_confirmed and request.form.get("confirm") != "true":
        flash(
            f"This listing has {future_confirmed} confirmed future appointment(s). "
            "Check the confirmation box to proceed with deletion.",
            "error",
        )
        return redirect(url_for("admin.listings"))

    if future_confirmed:
        appointments = db.session.scalars(
            db.select(Appointment).where(
                Appointment.listing_id == listing.id,
                Appointment.status == "confirmed",
                Appointment.starts_at > utcnow(),
            )
        ).all()
        for appointment in appointments:
            appointment.status = "cancelled"
            appointment.proposed_at = None
            if appointment.patient and appointment.patient.user:
                notify(appointment.patient.user, f"An appointment for '{listing.title}' was cancelled due to listing deletion.")
                send_email(
                    appointment.patient.user.email,
                    "Appointment cancelled",
                    "notice",
                    user=appointment.patient.user,
                    message=f"Your confirmed appointment for '{listing.title}' was cancelled because the listing was deleted.",
                )
            if appointment.student and appointment.student.user:
                notify(appointment.student.user, f"An appointment for '{listing.title}' was cancelled due to listing deletion.")
                send_email(
                    appointment.student.user.email,
                    "Appointment cancelled",
                    "notice",
                    user=appointment.student.user,
                    message=f"Your confirmed appointment for '{listing.title}' was cancelled because the listing was deleted.",
                )

    cover_filename = listing.cover_image
    application_count = db.session.scalar(
        db.select(db.func.count(PatientApplication.id)).where(PatientApplication.listing_id == listing.id)
    ) or 0
    appointment_count = db.session.scalar(
        db.select(db.func.count(Appointment.id)).where(Appointment.listing_id == listing.id)
    ) or 0

    audit_logger.admin_listing_deleted(
        actor=current_user,
        listing_id=listing.id,
        title=listing.title,
        applications_cascaded=application_count,
        appointments_unlinked=appointment_count,
    )
    db.session.delete(listing)
    db.session.commit()

    if cover_filename:
        try:
            filepath = get_upload_root() / "covers" / cover_filename
            if filepath.exists():
                filepath.unlink()
        except Exception:
            current_app.logger.warning("Failed to delete cover file: %s", cover_filename)

    flash("Listing deleted.", "success")
    return redirect(url_for("admin.listings"))


@bp.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
@login_required
def delete_appointment(appointment_id):
    """Hard delete an appointment and notify both parties."""
    admin_required()
    appointment = db.get_or_404(Appointment, appointment_id)
    title = appointment.listing.title if appointment.listing else "a listing"

    if appointment.patient and appointment.patient.user:
        notify(appointment.patient.user, f"An appointment for '{title}' was cancelled by an administrator.")
    if appointment.student and appointment.student.user:
        notify(appointment.student.user, f"An appointment for '{title}' was cancelled by an administrator.")

    audit_logger.admin_appointment_deleted(
        actor=current_user,
        appointment_id=appointment.id,
        listing_id=appointment.listing_id,
        patient_id=appointment.patient_id,
        student_id=appointment.student_id,
    )
    db.session.delete(appointment)
    db.session.commit()

    flash("Appointment deleted.", "success")
    return redirect(url_for("admin.appointments"))

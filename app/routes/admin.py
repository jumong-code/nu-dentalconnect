# Admin blueprint. Accounts, student approvals, listings,
# appointments, at audit history.
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


# Role guard. Admin lang ang makakapasok sa mga route dito.
def admin_required():
    if current_user.role != "admin":
        abort(403)


# Listahan ng accounts, may search at role filter.
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


# Activate o deactivate. Yung sariling account, hindi
# puwedeng i-deactivate.
@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    admin_required()
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own administrator account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    # Tinaasan yung version para mawala agad yung session ng
    # user sa lahat ng device.
    user.auth_version += 1
    audit_logger.admin_user_toggle(actor=current_user, target_user=user, is_active=user.is_active)
    db.session.commit()
    flash("Account status updated.", "success")
    return redirect(url_for("admin.users"))


# Admin ang mag-se-set ng password. Hindi ito para sa admin
# accounts, kaya may check sa role.
@bp.route("/users/<int:user_id>/set-password", methods=["GET", "POST"])
@login_required
def set_user_password(user_id):
    admin_required()
    user = db.get_or_404(User, user_id)
    if user.role == "admin":
        flash("Cannot set a password for administrator accounts.", "error")
        return redirect(url_for("admin.users"))

    form = AdminSetPasswordForm()
    if form.validate_on_submit():
        device = get_device_info(request)
        user.set_password(form.password.data)
        user.auth_version += 1
        audit_logger.password_admin_set(actor=current_user, target_user=user, device=device)
        db.session.commit()
        # Email, notification lang. Wala yung bagong password.
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


# Approval queue. Verified, active, pending lang ang kasama.
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


# Approve. Value error galing sa service, kaya friendly
# flash message lang.
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


# Reject = deactivate. Hindi binubura yung account.
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


# Lahat ng listings, kasama drafts at closed.
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


# Admin puwedeng magsara ng listing mula rito.
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


# Lahat ng appointments, newest first.
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


# Audit history na may action, actor, at date range filter.
@bp.route("/audit")
@login_required
def audit():
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
        # Manila date galing sa form, iko-convert sa UTC bago
        # ihambing sa created_at.
        if date_from:
            start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(AuditLog.created_at >= start)
        # Plus one day para kasama pa yung buong araw na pinili.
        if date_to:
            end = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(AuditLog.created_at < end)
    # Mali yung date format. Flash lang, hindi crash.
    except ValueError:
        flash("Use a valid date in the date filters.", "error")

    logs = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=50, max_per_page=50, error_out=False
    )
    actions = db.session.scalars(
        db.select(AuditLog.action).distinct().order_by(AuditLog.action)
    ).all()
    return render_template("admin/audit.html", logs=logs, actions=actions)


# Hard delete ng account. Kailangang i-type yung email para
# sigurado, at may check sa huling active admin.
@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    admin_required()
    user = db.get_or_404(User, user_id)

    if user.id == current_user.id:
        flash("You cannot delete your own administrator account.", "error")
        return redirect(url_for("admin.users"))

    # Bawal mawala yung huling admin, kasi walang makakapasok
    # para mag-approve ng ibang accounts.
    if user.role == "admin":
        active_admin_count = db.session.scalar(
            db.select(db.func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
        )
        if active_admin_count <= 1:
            flash("Cannot delete the last active administrator.", "error")
            return redirect(url_for("admin.users"))

    # May confirmed future appointment pa, hindi muna puwedeng
    # burahin yung user.
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

    # Typed email ang confirmation. Pag hindi tugma, cancel.
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


# Bura ng listing. May confirmation din kung may future
# confirmed appointments.
@bp.route("/listings/<int:listing_id>/delete", methods=["POST"])
@login_required
def delete_listing(listing_id):
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


# Bura ng appointment record, tapos notify yung dalawang
# panig.
@bp.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
@login_required
def delete_appointment(appointment_id):
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

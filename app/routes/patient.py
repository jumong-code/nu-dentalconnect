from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..forms import ApplicationForm, AppointmentForm
from ..models import Appointment, DentistryStudent, PatientApplication, RecruitmentListing, utcnow
from ..audit import audit_logger
from ..services import confirm_appointment, has_active_student_booking, notify, send_email

bp = Blueprint("patient", __name__)


def patient_required():
    if current_user.role != "patient":
        abort(403)


@bp.route("/opportunities/<int:listing_id>/apply", methods=["POST"])
@bp.route("/appointments/<int:listing_id>/apply", methods=["POST"])
@login_required
def apply(listing_id):
    patient_required()
    listing = db.get_or_404(RecruitmentListing, listing_id)
    if listing.status != "published":
        abort(404)
    form = ApplicationForm()
    if form.validate_on_submit():
        application = PatientApplication(listing=listing, patient=current_user.patient_profile, message=form.message.data or None)
        db.session.add(application)
        db.session.flush()
        audit_logger.application_created(actor=current_user, application_id=application.id, listing_id=listing.id, listing_title=listing.title)
        notify(listing.student.user, f"New patient application for '{listing.title}'.")
        try:
            db.session.commit()
            send_email(listing.student.user.email, "A patient applied for your procedure listing", "notice", user=listing.student.user, message=f"A patient applied for '{listing.title}'. Sign in to review the patient application.")
            flash("Your application has been sent.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("You have already applied to this procedure listing.", "info")
    else:
        flash("Please review your application details and try again.", "error")
    return redirect(url_for("main.opportunity_detail", listing_id=listing.id))


@bp.route("/applications/<int:application_id>/withdraw", methods=["POST"])
@login_required
def withdraw(application_id):
    patient_required()
    application = db.get_or_404(PatientApplication, application_id)
    if application.patient_id != current_user.patient_profile.id:
        abort(403)
    if application.status == "pending":
        application.status = "withdrawn"
        audit_logger.application_withdrawn(actor=current_user, application_id=application.id)
        db.session.commit()
        flash("Application withdrawn.", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/opportunities/<int:listing_id>/appointments", methods=["GET", "POST"])
@bp.route("/appointments/<int:listing_id>/request", methods=["GET", "POST"])
@login_required
def request_appointment(listing_id):
    patient_required()
    listing = db.get_or_404(RecruitmentListing, listing_id)
    if listing.status != "published":
        abort(404)
    form = AppointmentForm()
    if form.validate_on_submit():
        starts_at = form.starts_at.data
        if starts_at <= utcnow():
            flash("Choose a date and time in the future.", "error")
        else:
            db.session.execute(db.select(DentistryStudent.id).where(DentistryStudent.id == listing.student_id).with_for_update())
            if has_active_student_booking(listing.student_id, current_user.patient_profile.id, starts_at):
                db.session.rollback()
                flash("You already have an active appointment request near that time with this student.", "info")
            else:
                appointment = Appointment(patient=current_user.patient_profile, student=listing.student, listing=listing, starts_at=starts_at, location=listing.location, note=form.note.data or None)
                db.session.add(appointment)
                db.session.flush()
                audit_logger.appointment_requested(actor=current_user, appointment_id=appointment.id, listing_id=listing.id, listing_title=listing.title, starts_at=appointment.starts_at.isoformat())
                notify(listing.student.user, f"New appointment request for '{listing.title}'.")
                db.session.commit()
                send_email(listing.student.user.email, "New appointment request", "notice", user=listing.student.user, message=f"A patient requested an appointment for '{listing.title}'. Sign in to respond.")
                flash("Appointment request sent. The student will confirm or propose another time.", "success")
                return redirect(url_for("main.dashboard"))
    return render_template("appointments/request.html", form=form, listing=listing)


@bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@login_required
def cancel_appointment(appointment_id):
    patient_required()
    appointment = db.get_or_404(Appointment, appointment_id)
    if appointment.patient_id != current_user.patient_profile.id:
        abort(403)
    if appointment.can_cancel():
        appointment.status = "cancelled"
        audit_logger.appointment_cancelled(actor=current_user, appointment_id=appointment.id)
        notify(appointment.student.user, "A patient cancelled an appointment.")
        db.session.commit()
        flash("Appointment cancelled.", "success")
    else:
        flash("This appointment can no longer be cancelled.", "error")
    return redirect(url_for("main.dashboard"))


@bp.route("/appointments/<int:appointment_id>/reschedule", methods=["POST"])
@login_required
def reschedule(appointment_id):
    patient_required()
    appointment = db.get_or_404(Appointment, appointment_id)
    if appointment.patient_id != current_user.patient_profile.id:
        abort(403)
    form = AppointmentForm()
    if form.validate_on_submit() and appointment.status in {"pending", "confirmed"} and form.starts_at.data > utcnow():
        appointment.proposed_at = form.starts_at.data
        appointment.status = "reschedule_requested"
        audit_logger.appointment_rescheduled(actor=current_user, appointment_id=appointment.id, proposed_at=str(appointment.proposed_at))
        notify(appointment.student.user, "A patient requested to reschedule an appointment.")
        db.session.commit()
        flash("Reschedule request sent.", "success")
    else:
        flash("Unable to request that schedule change.", "error")
    return redirect(url_for("main.dashboard"))


@bp.route("/appointments/<int:appointment_id>/accept-proposal", methods=["POST"])
@login_required
def accept_proposal(appointment_id):
    patient_required()
    appointment = db.get_or_404(Appointment, appointment_id)
    if appointment.patient_id != current_user.patient_profile.id:
        abort(403)
    if appointment.status != "reschedule_requested" or not appointment.proposed_at:
        abort(400)
    appointment.starts_at = appointment.proposed_at
    if not confirm_appointment(appointment):
        db.session.rollback()
        flash("That proposed time has passed or conflicts with another confirmed appointment.", "error")
        return redirect(url_for("main.dashboard"))
    appointment.proposed_at = None
    audit_logger.appointment_confirmed(actor=current_user, appointment_id=appointment.id)
    notify(appointment.student.user, "The patient accepted your proposed appointment time.")
    db.session.commit()
    send_email(appointment.student.user.email, "Appointment time accepted", "notice", user=appointment.student.user, message="The patient accepted your proposed appointment time.")
    flash("The proposed time is confirmed.", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
@login_required
def delete_appointment(appointment_id):
    """Hard delete an appointment (only for non-confirmed appointments)."""
    patient_required()
    appointment = db.get_or_404(Appointment, appointment_id)
    if appointment.patient_id != current_user.patient_profile.id:
        abort(403)

    # Only allow hard delete for pending, rejected, withdrawn, cancelled appointments
    # Confirmed and completed appointments should use cancel flow
    if appointment.status not in {"pending", "rejected", "withdrawn", "cancelled"}:
        flash("This appointment cannot be deleted. Use cancel instead.", "error")
        return redirect(url_for("main.dashboard"))

    audit_logger.appointment_deleted(actor=current_user, appointment_id=appointment.id)
    db.session.delete(appointment)
    db.session.commit()

    flash("Appointment deleted.", "success")
    return redirect(url_for("main.dashboard"))

# Student blueprint. CRUD ng listing, templates, at pang-sagot
# sa applications at appointments.
import secrets
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from ..extensions import db
from ..forms import ListingForm, ScheduleForm
from ..models import Appointment, Patient, PatientApplication, RecruitmentListing, StudentListingTemplate, utcnow
from ..listing_presets import listing_template_data, BUILT_IN_LISTING_TEMPLATES
from ..audit import audit_logger
from ..services import confirm_appointment, notify, send_email
from ..upload import upload_listing_cover, get_upload_root, MAX_LISTING_IMAGE_SIZE

bp = Blueprint("student", __name__)


# Role guard para sa lahat ng student route.
def student_required():
    if current_user.role != "student":
        abort(403)


# Pag hindi kanya yung listing, 403. Dito nakalagay yung
# ownership check kaya hindi na paulit-ulit.
def owned_listing(listing_id):
    listing = db.get_or_404(RecruitmentListing, listing_id)
    if listing.student_id != current_user.student_profile.id:
        abort(403)
    return listing


# Templates ng naka-login na student lang ang kinukuha ko.
def owned_listing_templates():
    return StudentListingTemplate.query.filter_by(
        student_id=current_user.student_profile.id
    ).order_by(StudentListingTemplate.name.asc(), StudentListingTemplate.id.asc()).limit(100).all()


# Isang renderer para sa create at edit, para pareho yung
# template at data na pinapasa.
def render_listing_form(form, title, listing=None):
    saved_templates = owned_listing_templates()
    return render_template(
        "student/listing_form.html",
        form=form,
        title=title,
        listing=listing,
        templates=saved_templates,
        template_data=listing_template_data(saved_templates),
    )


# Save as template, hindi listing. Kaya may flash na
# nagsasabing hindi pa naka-save yung listing.
def save_listing_template(form, title, listing=None):
    name = (form.template_name.data or "").strip()
    if not name:
        form.template_name.errors.append("Enter a name for your saved template.")
        flash("Add a template name, then save it again.", "error")
        return render_listing_form(form, title, listing)

    template = StudentListingTemplate(
        student_id=current_user.student_profile.id,
        name=name,
        title=form.title.data.strip(),
        category=form.category.data.strip(),
        location=form.location.data.strip(),
        preferred_schedule=form.preferred_schedule.data.strip(),
        description=form.description.data.strip(),
        eligibility=form.eligibility.data.strip(),
    )
    db.session.add(template)
    db.session.flush()
    audit_logger.template_created(actor=current_user, template_id=template.id, name=template.name)
    db.session.commit()
    flash(f"'{name}' is saved to your appointment templates. Your listing has not been saved.", "success")
    form.template_name.data = ""
    return render_listing_form(form, title, listing)


# Gawa ng listing. Yung submission_key ang humaharang sa
# doble submit galing sa double click.
@bp.route("/listings/new", methods=["GET", "POST"])
@login_required
def create_listing():
    student_required()
    form = ListingForm()
    if request.method == "GET":
        # Bagong random key kada GET, para isang POST lang ang
        # makakagawa ng listing.
        form.submission_key.data = secrets.token_urlsafe(32)
        template_id = request.args.get("template", "").strip()
        # Puwedeng mag-prefill galing sa built-in o saved template,
        # pero editable pa rin bago i-save.
        if template_id:
            template_data = None
            if template_id in [t["id"] for t in BUILT_IN_LISTING_TEMPLATES]:
                template_data = next(t for t in BUILT_IN_LISTING_TEMPLATES if t["id"] == template_id)
            elif template_id.startswith("saved-"):
                try:
                    saved_id = int(template_id.replace("saved-", ""))
                    saved = db.get_or_404(StudentListingTemplate, saved_id)
                    if saved.student_id == current_user.student_profile.id:
                        template_data = {
                            "title": saved.title,
                            "category": saved.category,
                            "location": saved.location,
                            "preferred_schedule": saved.preferred_schedule,
                            "description": saved.description,
                            "eligibility": saved.eligibility,
                        }
                except (ValueError, TypeError):
                    pass
            if template_data:
                form.title.data = template_data.get("title", "")
                form.category.data = template_data.get("category", "")
                form.location.data = template_data.get("location", "")
                form.preferred_schedule.data = template_data.get("preferred_schedule", "")
                form.description.data = template_data.get("description", "")
                form.eligibility.data = template_data.get("eligibility", "")
    if form.validate_on_submit():
        if "save_listing_template" in request.form:
            return save_listing_template(form, "Post an appointment listing")
        # May listing na may parehong key, ibig sabihin na-submit na
        # ito dati. I-redirect ko na lang sa edit page.
        existing = db.session.scalar(db.select(RecruitmentListing).where(RecruitmentListing.submission_key == form.submission_key.data, RecruitmentListing.student_id == current_user.student_profile.id))
        if existing:
            return redirect(url_for("student.edit_listing", listing_id=existing.id))
        listing = RecruitmentListing(student=current_user.student_profile, title=form.title.data, category=form.category.data, location=form.location.data, preferred_schedule=form.preferred_schedule.data, description=form.description.data, eligibility=form.eligibility.data, status="published" if form.publish_now.data else "draft", submission_key=form.submission_key.data)
        db.session.add(listing)
        db.session.flush()
        audit_logger.listing_created(actor=current_user, listing_id=listing.id, status=listing.status)

        # Cover optional. Pag invalid yung image, balik sa form na
        # may error, hindi ko muna isasave yung listing.
        if "cover" in request.files:
            file = request.files["cover"]
            if file and file.filename:
                success, error, filename = upload_listing_cover(file, listing, None)
                if not success:
                    flash(error, "error")
                    return render_listing_form(form, "Post an appointment listing")
                listing.cover_image = filename
                audit_logger.cover_uploaded(actor=current_user, listing_id=listing.id)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = db.session.scalar(db.select(RecruitmentListing).where(RecruitmentListing.submission_key == form.submission_key.data, RecruitmentListing.student_id == current_user.student_profile.id))
            if existing:
                return redirect(url_for("student.edit_listing", listing_id=existing.id))
            raise
        flash("Appointment listing published." if listing.status == "published" else "Appointment listing saved as a draft.", "success")
        return redirect(url_for("student.edit_listing", listing_id=listing.id))
    return render_listing_form(form, "Post an appointment listing")


# Edit ng listing. Bagong submission_key din kada GET para
# hindi magamit ulit yung lumang form.
@bp.route("/listings/<int:listing_id>/edit", methods=["GET", "POST"])
@login_required
def edit_listing(listing_id):
    student_required()
    listing = owned_listing(listing_id)
    form = ListingForm(obj=listing)
    if request.method == "GET":
        form.submission_key.data = secrets.token_urlsafe(32)
    if form.validate_on_submit():
        if "save_listing_template" in request.form:
            return save_listing_template(form, "Edit appointment listing", listing)
        for field in ("title", "category", "location", "preferred_schedule", "description", "eligibility"):
            setattr(listing, field, getattr(form, field).data)
        # Closed na listing, hindi na puwedeng i-publish ulit.
        # Kailangan gumawa ng bago.
        if form.publish_now.data and listing.status == "closed":
            flash("Closed listings cannot be published again. Create a new listing.", "error")
            return render_listing_form(form, "Edit appointment listing", listing)
        if form.publish_now.data:
            listing.status = "published"

        if "cover" in request.files:
            file = request.files["cover"]
            if file and file.filename:
                old_filename = listing.cover_image
                success, error, filename = upload_listing_cover(file, listing, old_filename)
                if not success:
                    flash(error, "error")
                    return render_listing_form(form, "Edit appointment listing", listing)
                listing.cover_image = filename
                audit_logger.cover_uploaded(actor=current_user, listing_id=listing.id)

        audit_logger.listing_updated(actor=current_user, listing_id=listing.id, status=listing.status)
        db.session.commit()
        flash("Appointment listing updated.", "success")
        return redirect(url_for("main.dashboard"))
    return render_listing_form(form, "Edit appointment listing", listing)


# Saved templates, may pagination, plus yung built-in na
# hindi naeedit ng student.
@bp.route("/listing-templates")
@login_required
def listing_templates():
    student_required()
    saved_templates = StudentListingTemplate.query.filter_by(student_id=current_user.student_profile.id).order_by(StudentListingTemplate.name.asc(), StudentListingTemplate.id.asc()).paginate(page=request.args.get("page", 1, type=int), per_page=20, max_per_page=20, error_out=False)
    built_in = BUILT_IN_LISTING_TEMPLATES
    return render_template("student/listing_templates.html", templates=saved_templates, built_in=built_in)


# Bura ng template. Sariling template lang, at hindi ito
# umaapekto sa mga listing na nagamit na.
@bp.route("/listing-templates/<int:template_id>/delete", methods=["POST"])
@login_required
def delete_listing_template(template_id):
    student_required()
    template = db.get_or_404(StudentListingTemplate, template_id)
    if template.student_id != current_user.student_profile.id:
        abort(403)
    db.session.delete(template)
    audit_logger.template_deleted(actor=current_user, template_id=template.id)
    db.session.commit()
    flash("Saved appointment template deleted.", "success")
    return redirect(url_for("student.listing_templates"))


# Status change na may allowed transitions. Kung wala sa
# listahan, 400, para hindi makalundag sa invalid state.
@bp.route("/listings/<int:listing_id>/status/<status>", methods=["POST"])
@login_required
def listing_status(listing_id, status):
    student_required()
    listing = owned_listing(listing_id)
    transitions = {"draft": {"draft", "published"}, "published": {"published", "draft", "closed"}, "closed": {"closed", "draft"}}
    if status not in transitions.get(listing.status, set()):
        abort(400)
    listing.status = status
    audit_logger.listing_status_changed(actor=current_user, listing_id=listing.id, status=status)
    db.session.commit()
    flash(f"Appointment listing {status}.", "success")
    return redirect(url_for("main.dashboard"))


# Bura ng listing. Pag may future confirmed appointment,
# kailangan muna ng explicit na confirmation.
@bp.route("/listings/<int:listing_id>/delete", methods=["POST"])
@login_required
def delete_listing(listing_id):
    student_required()
    listing = owned_listing(listing_id)

    future_confirmed = 0
    if listing.status != "closed":
        # Bilangin muna yung confirmed sa hinaharap. Closed listing,
        # wala nang aalalahanin.
        future_confirmed = db.session.scalar(
            db.select(db.func.count(Appointment.id)).where(
                Appointment.listing_id == listing.id,
                Appointment.status == "confirmed",
                Appointment.starts_at > utcnow()
            )
        )

    confirm = request.form.get("confirm") == "true"
    # Walang checkbox, hindi ko tutuloy yung delete.
    if future_confirmed and not confirm:
        flash(f"This listing has {future_confirmed} confirmed future appointment(s). Check the confirmation box to proceed with deletion.", "error")
        return redirect(url_for("main.dashboard"))

    if future_confirmed:
        # Bago burahin yung listing, i-cancel at i-notify yung mga
        # patient na may confirmed na appointment.
        appointments = db.session.scalars(
            db.select(Appointment).where(
                Appointment.listing_id == listing.id,
                Appointment.status == "confirmed",
                Appointment.starts_at > utcnow()
            )
        ).all()
        for appt in appointments:
            appt.status = "cancelled"
            appt.proposed_at = None
            if appt.patient and appt.patient.user:
                notify(appt.patient.user, f"An appointment for '{listing.title}' was cancelled by the student.")
                try:
                    from ..services import send_email
                    send_email(appt.patient.user.email, "Appointment cancelled", "notice",
                              user=appt.patient.user, message=f"Your confirmed appointment for '{listing.title}' was cancelled by the student.")
                except Exception:
                    pass

    cover_filename = listing.cover_image

    application_count = db.session.scalar(db.select(db.func.count(PatientApplication.id)).where(PatientApplication.listing_id == listing.id)) or 0
    appointment_count = db.session.scalar(db.select(db.func.count(Appointment.id)).where(Appointment.listing_id == listing.id)) or 0
    audit_logger.listing_deleted(
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
            from ..upload import get_upload_root
            filepath = get_upload_root() / "covers" / cover_filename
            if filepath.exists():
                filepath.unlink()
        except Exception:
            current_app.logger.warning(f"Failed to delete cover file: {cover_filename}")

    flash("Appointment listing deleted.", "success")
    return redirect(url_for("main.dashboard"))


# Accept o reject ng application. Pending lang ang puwedeng
# desisyunan, tapos notify at email yung patient.
@bp.route("/applications/<int:application_id>/<decision>", methods=["POST"])
@login_required
def application_decision(application_id, decision):
    student_required()
    application = db.get_or_404(PatientApplication, application_id)
    if application.listing.student_id != current_user.student_profile.id:
        abort(403)
    if decision not in {"accepted", "rejected"} or application.status != "pending":
        abort(400)
    application.status = decision
    audit_logger.application_decision(actor=current_user, application_id=application.id, decision=decision)
    notify(application.patient.user, f"Your application for '{application.listing.title}' was {decision}.")
    db.session.commit()
    send_email(application.patient.user.email, "Your patient application was updated", "notice", user=application.patient.user, message=f"Your patient application for '{application.listing.title}' was {decision}.")
    flash(f"Application {decision}.", "success")
    return redirect(url_for("student.listing_applications", listing_id=application.listing_id))


# Applications ng isang listing. Paginated para hindi
# mabigat kung marami.
@bp.route("/listings/<int:listing_id>/applications")
@login_required
def listing_applications(listing_id):
    student_required()
    listing = owned_listing(listing_id)
    applications = PatientApplication.query.options(joinedload(PatientApplication.patient).joinedload(Patient.user)).filter_by(listing_id=listing.id).order_by(PatientApplication.created_at.desc(), PatientApplication.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=20, max_per_page=20, error_out=False)
    return render_template("student/applications.html", listing=listing, applications=applications)


# Lahat ng applications sa lahat ng listing ng student.
@bp.route("/applications")
@login_required
def applications():
    student_required()
    applications_page = PatientApplication.query.join(RecruitmentListing).options(
        joinedload(PatientApplication.patient).joinedload(Patient.user),
        joinedload(PatientApplication.listing),
    ).filter(
        RecruitmentListing.student_id == current_user.student_profile.id
    ).order_by(
        PatientApplication.created_at.desc(), PatientApplication.id.desc()
    ).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, max_per_page=20, error_out=False
    )
    return render_template("student/applications_all.html", applications=applications_page)


# Kunin yung appointment tapos check kung sa kanya.
# 404 kung wala, 403 kung hindi kanya.
def owned_appointment(appointment_id):
    appointment = db.session.scalar(db.select(Appointment).options(joinedload(Appointment.patient).joinedload(Patient.user), joinedload(Appointment.listing)).where(Appointment.id == appointment_id))
    if appointment is None:
        abort(404)
    if appointment.student_id != current_user.student_profile.id:
        abort(403)
    return appointment


# Bura ng appointment record. Kahit anong status, kanya
# yung listing, kaya puwede niyang tanggalin.
@bp.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
@login_required
def delete_appointment(appointment_id):
    student_required()
    appointment = owned_appointment(appointment_id)
    title = appointment.listing.title if appointment.listing else "your appointment"
    patient_user = appointment.patient.user if appointment.patient else None
    audit_logger.appointment_deleted(actor=current_user, appointment_id=appointment.id)
    if patient_user:
        notify(patient_user, f"Your appointment for '{title}' was removed by the dentistry student.")
    db.session.delete(appointment)
    db.session.commit()
    if patient_user:
        send_email(
            patient_user.email,
            "Appointment removed",
            "notice",
            user=patient_user,
            message=f"Your appointment for '{title}' was removed by the dentistry student. Sign in to review your appointments.",
        )
    flash("Appointment deleted.", "success")
    return redirect(url_for("student.appointments"))


# Cancel lang ng upcoming. Yung can_cancel() ang boundary.
@bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@login_required
def cancel_appointment(appointment_id):
    student_required()
    appointment = owned_appointment(appointment_id)
    if not appointment.can_cancel():
        flash("Only upcoming appointments can be cancelled.", "error")
        return redirect(url_for("student.appointments"))

    title = appointment.listing.title if appointment.listing else "your appointment"
    patient_user = appointment.patient.user if appointment.patient else None
    appointment.status = "cancelled"
    appointment.proposed_at = None
    audit_logger.appointment_cancelled(actor=current_user, appointment_id=appointment.id)
    if patient_user:
        notify(patient_user, f"Your appointment for '{title}' was cancelled by the dentistry student.")
    db.session.commit()
    if patient_user:
        send_email(
            patient_user.email,
            "Appointment cancelled",
            "notice",
            user=patient_user,
            message=f"Your appointment for '{title}' was cancelled by the dentistry student.",
        )
    flash("Appointment cancelled. The patient was notified.", "success")
    return redirect(url_for("student.appointments"))


# Lahat ng appointments ng student, may pagination.
@bp.route("/appointments")
@login_required
def appointments():
    student_required()
    page = Appointment.query.options(
        joinedload(Appointment.patient).joinedload(Patient.user),
        joinedload(Appointment.listing),
    ).filter_by(student_id=current_user.student_profile.id).order_by(
        Appointment.starts_at.desc(), Appointment.id.desc()
    ).paginate(page=request.args.get("page", 1, type=int), per_page=25, max_per_page=25, error_out=False)
    return render_template("student/appointments.html", appointments=page, now_utc=utcnow())


# Tatlong decision: confirm, reject, complete. Bawat isa
# may status check bago magbago.
@bp.route("/appointments/<int:appointment_id>/<decision>", methods=["POST"])
@login_required
def appointment_decision(appointment_id, decision):
    student_required()
    appointment = owned_appointment(appointment_id)
    if decision == "confirm":
        if appointment.status not in {"pending", "reschedule_requested"}:
            abort(400)
        # Kung may proposed time, yun ang gagamitin; kundi yung
        # orihinal. Conflict check pa rin bago i-confirm.
        appointment.starts_at = appointment.proposed_at or appointment.starts_at
        if not confirm_appointment(appointment):
            db.session.rollback()
            flash("That time has passed or conflicts with another confirmed appointment.", "error")
            return redirect(url_for("main.dashboard"))
        appointment.proposed_at = None
        audit_logger.appointment_confirmed(actor=current_user, appointment_id=appointment.id)
        message = "Your appointment is confirmed."
    elif decision == "reject":
        if appointment.status not in {"pending", "reschedule_requested"}:
            abort(400)
        appointment.status = "rejected"
        audit_logger.appointment_rejected(actor=current_user, appointment_id=appointment.id)
        message = "Your appointment request was declined."
    # Completed lang kung confirmed at tapos na yung oras.
    elif decision == "complete":
        if appointment.status != "confirmed" or appointment.starts_at > utcnow():
            abort(400)
        appointment.status = "completed"
        audit_logger.appointment_completed(actor=current_user, appointment_id=appointment.id)
        message = "Your appointment has been marked complete."
    else:
        abort(400)
    notify(appointment.patient.user, message)
    db.session.commit()
    send_email(appointment.patient.user.email, "Appointment update", "notice", user=appointment.patient.user, message=message)
    flash("Appointment updated.", "success")
    return redirect(url_for("main.dashboard"))


# Bagong oras mula sa student. Oras pa rin ang unang
# check bago maipadala sa patient.
@bp.route("/appointments/<int:appointment_id>/propose", methods=["POST"])
@login_required
def propose_schedule(appointment_id):
    student_required()
    appointment = owned_appointment(appointment_id)
    form = ScheduleForm()
    if appointment.status not in {"pending", "confirmed", "reschedule_requested"} or not form.validate_on_submit() or form.proposed_at.data <= utcnow():
        flash("Choose a valid future time for this appointment.", "error")
        return redirect(url_for("main.dashboard"))
    appointment.proposed_at = form.proposed_at.data
    appointment.status = "reschedule_requested"
    audit_logger.appointment_proposed(actor=current_user, appointment_id=appointment.id, proposed_at=str(appointment.proposed_at))
    notify(appointment.patient.user, "Your student proposed a different appointment time.")
    db.session.commit()
    flash("Alternative time sent to the patient.", "success")
    return redirect(url_for("main.dashboard"))


# Upload ng cover mula sa edit page.
@bp.route("/listings/<int:listing_id>/cover", methods=["POST"])
@login_required
def upload_cover(listing_id):
    student_required()
    listing = owned_listing(listing_id)

    if "cover" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("student.edit_listing", listing_id=listing.id))

    file = request.files["cover"]
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("student.edit_listing", listing_id=listing.id))

    old_filename = listing.cover_image
    success, error, filename = upload_listing_cover(file, listing, old_filename)
    if not success:
        flash(error, "error")
        return redirect(url_for("student.edit_listing", listing_id=listing.id))

    listing.cover_image = filename
    audit_logger.cover_uploaded(actor=current_user, listing_id=listing.id)
    db.session.commit()
    flash("Cover image updated.", "success")
    return redirect(url_for("student.edit_listing", listing_id=listing.id))


# Tanggal ng cover. Yung file sa disk, binubura pagkatapos
# ng commit.
@bp.route("/listings/<int:listing_id>/cover/remove", methods=["POST"])
@login_required
def remove_cover(listing_id):
    student_required()
    listing = owned_listing(listing_id)

    if listing.cover_image:
        old_filename = listing.cover_image
        listing.cover_image = None
        db.session.commit()
        try:
            filepath = get_upload_root() / "covers" / old_filename
            if filepath.exists():
                filepath.unlink()
        except Exception:
            current_app.logger.warning(f"Failed to delete cover file: {old_filename}")
        flash("Cover image removed.", "success")
    else:
        flash("No cover image to remove.", "info")

    audit_logger.cover_removed(actor=current_user, listing_id=listing.id)
    db.session.commit()
    return redirect(url_for("student.edit_listing", listing_id=listing.id))

# Main blueprint: public pages, dashboard, profile, at
# pag-serve ng uploads.
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for, send_file
from flask_login import current_user, login_required, logout_user
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Appointment, DentistryStudent, Notification, Patient, PatientApplication, RecruitmentListing, User
from ..forms import ChangePasswordForm, ProfileForm
from ..services import issue_email_otp, revoke_email_otps
from ..upload import (
    get_avatar_path, get_listing_cover_path,
    can_view_patient_avatar, can_view_student_avatar, can_view_listing_cover,
    upload_patient_avatar, upload_student_avatar, upload_listing_cover,
    MAX_PROFILE_IMAGE_SIZE, MAX_LISTING_IMAGE_SIZE
)
from ..profile_policy import ProfileAccessPolicy, AccessResult
from ..formatters import FieldFormatter
from ..audit import audit_logger, get_device_info

bp = Blueprint("main", __name__)


# Home page. Published at approved lang ang pinapakita, tatlo
# lang para mabilis mag-load.
@bp.route("/")
def index():
    listings = RecruitmentListing.query.join(DentistryStudent).join(
        User, DentistryStudent.user_id == User.id
    ).filter(
        RecruitmentListing.status == "published",
        User.is_active.is_(True),
        User.approval_status == "approved",
    ).order_by(RecruitmentListing.created_at.desc()).limit(3).all()
    return render_template("index.html", listings=listings)


# About page. Static content lang, walang query.
@bp.route("/about")
def about():
    return render_template("about.html")


# Isang route, tatlong dashboard depende sa role. Iba-iba
# yung query, pero iisa lang yung base template.
@bp.route("/dashboard")
@login_required
def dashboard():
    from ..models import Patient, DentistryStudent, Notification, utcnow
    # Patient: appointments at applications niya, plus huling
    # limang notifications.
    if current_user.role == "patient":
        patient = current_user.patient_profile
        appointments = Appointment.query.options(joinedload(Appointment.student).joinedload(DentistryStudent.user), joinedload(Appointment.listing)).filter_by(patient_id=patient.id).order_by(Appointment.starts_at.desc(), Appointment.id.desc()).all()
        applications = PatientApplication.query.options(joinedload(PatientApplication.listing)).filter_by(patient_id=patient.id).order_by(PatientApplication.created_at.desc()).limit(5).all()
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
        return render_template("dashboard/patient.html", appointments=appointments, applications=applications, notifications=notifications, now_utc=utcnow())
    # Student: listings, applications, at requests na kailangan
    # sagutin. May pagination yung listings.
    if current_user.role == "student":
        student = current_user.student_profile
        listings_page = RecruitmentListing.query.filter_by(student_id=student.id).order_by(RecruitmentListing.created_at.desc(), RecruitmentListing.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=10, max_per_page=10, error_out=False)
        listings = listings_page.items
        published_listing_count = RecruitmentListing.query.filter_by(student_id=student.id, status="published").count()
        listing_ids = [listing.id for listing in listings]
        application_counts = dict(db.session.execute(
            db.select(PatientApplication.listing_id, db.func.count(PatientApplication.id))
            .where(PatientApplication.listing_id.in_(listing_ids))
            .group_by(PatientApplication.listing_id)
        ).all()) if listing_ids else {}
        apps = PatientApplication.query.join(RecruitmentListing).filter(RecruitmentListing.student_id == student.id)
        appointment_options = (
            joinedload(Appointment.patient).joinedload(Patient.user),
            joinedload(Appointment.listing),
        )
        appointments = Appointment.query.options(*appointment_options).filter(
            Appointment.student_id == student.id,
            # Hindi ko nililimitahan yung pending at reschedule requests,
            # para hindi mawala sa student yung hindi pa nasasagot.
            Appointment.status.in_(["pending", "reschedule_requested"]),
        ).order_by(Appointment.created_at.desc(), Appointment.id.desc()).all()
        confirmed_appointments = Appointment.query.options(*appointment_options).filter_by(
            student_id=student.id, status="confirmed"
        ).order_by(Appointment.starts_at.asc(), Appointment.id.asc()).all()
        appointment_counts = db.session.execute(db.select(
            Appointment.status, db.func.count(Appointment.id)
        ).where(Appointment.student_id == student.id, Appointment.status.in_(["confirmed", "pending", "reschedule_requested"])).group_by(Appointment.status)).all()
        appointment_counts = dict(appointment_counts)
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
        return render_template("dashboard/student.html", listings=listings, listing_page=listings_page, published_listing_count=published_listing_count, application_counts=application_counts, pending_applications=apps.filter_by(status="pending").count(), applicants=apps.count(), appointments=appointments, confirmed_appointments=confirmed_appointments, appointment_counts=appointment_counts, notifications=notifications, now_utc=utcnow())
    # Admin: bilang lang, lahat galing sa live queries.
    stats = {
        "users": User.query.count(),
        "patients": User.query.filter_by(role="patient").count(),
        "students": User.query.filter_by(role="student").count(),
        "pending_students": User.query.filter_by(
            role="student", approval_status="pending", email_verified=True, is_active=True
        ).count(),
        "listings": RecruitmentListing.query.join(DentistryStudent).join(
            User, DentistryStudent.user_id == User.id
        ).filter(
            RecruitmentListing.status == "published",
            User.is_active.is_(True),
            User.approval_status == "approved",
        ).count(),
        "appointments": Appointment.query.count(),
        "applications": PatientApplication.query.filter_by(status="pending").count(),
    }
    return render_template("dashboard/admin.html", stats=stats)


# Browse page. Search, category, at schedule filter, lahat
# nasa query string para ma-share yung link.
@bp.route("/opportunities")
@bp.route("/appointments")
def opportunities():
    query = RecruitmentListing.query.options(joinedload(RecruitmentListing.student).joinedload(DentistryStudent.user)).join(DentistryStudent).join(User, DentistryStudent.user_id == User.id).filter(RecruitmentListing.status == "published", User.is_active.is_(True), User.approval_status == "approved")
    keyword = request.args.get("q", "").strip()[:80]
    category = request.args.get("category", "").strip()[:100]
    availability = request.args.get("availability", "").strip()[:80]
    # ILIKE para hindi case-sensitive. Parameterized query ito,
    # kaya hindi puwedeng ma-inject ng SQL.
    if keyword:
        query = query.filter(db.or_(RecruitmentListing.title.ilike(f"%{keyword}%"), RecruitmentListing.description.ilike(f"%{keyword}%"), RecruitmentListing.category.ilike(f"%{keyword}%")))
    if category:
        query = query.filter(RecruitmentListing.category == category)
    if availability:
        query = query.filter(RecruitmentListing.preferred_schedule.ilike(f"%{availability}%"))
    listings = query.order_by(RecruitmentListing.created_at.desc(), RecruitmentListing.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=9, max_per_page=9, error_out=False)
    # Para sa naka-login na patient: may existing application na
    # ba siya sa mga listing sa page na ito.
    applied_statuses = {}
    if current_user.is_authenticated and current_user.role == "patient" and current_user.patient_profile:
        page_listing_ids = [listing.id for listing in listings.items]
        if page_listing_ids:
            applied_statuses = dict(db.session.execute(
                db.select(PatientApplication.listing_id, PatientApplication.status)
                .where(
                    PatientApplication.patient_id == current_user.patient_profile.id,
                    PatientApplication.listing_id.in_(page_listing_ids),
                )
            ).all())
    # Dropdown ng categories. Published at approved lang ang
    # pinagkukunan, para walang draft na lumabas.
    categories = db.session.scalars(
        db.select(RecruitmentListing.category)
        .join(DentistryStudent)
        .join(User, DentistryStudent.user_id == User.id)
        .where(
            RecruitmentListing.status == "published",
            User.is_active.is_(True),
            User.approval_status == "approved",
        )
        .distinct()
        .order_by(RecruitmentListing.category)
        .limit(100)
    ).all()
    return render_template("recruitment/browse.html", listings=listings, categories=categories, applied_statuses=applied_statuses)


# Detail page ng listing. Dalawang URL ito, pang-backward
# compatible sa lumang path.
@bp.route("/opportunities/<int:listing_id>")
@bp.route("/appointments/<int:listing_id>")
def opportunity_detail(listing_id):
    listing = db.get_or_404(RecruitmentListing, listing_id)
    is_owner = bool(
        current_user.is_authenticated
        and current_user.role == "student"
        and current_user.student_profile
        and current_user.student_profile.id == listing.student_id
    )
    is_admin = current_user.is_authenticated and current_user.role == "admin"
    # Owner at admin lang ang puwedeng tumingin ng draft o closed.
    # Sa iba, 404 para hindi mabisto na may tinatago.
    if not (is_owner or is_admin):
        if (
            listing.status != "published"
            or not listing.student.user.is_active
            or listing.student.user.approval_status != "approved"
        ):
            abort(404)
    application_status = None
    if current_user.is_authenticated and current_user.role == "patient" and current_user.patient_profile:
        application_status = db.session.scalar(db.select(PatientApplication.status).where(
            PatientApplication.listing_id == listing.id,
            PatientApplication.patient_id == current_user.patient_profile.id,
        ))
    return render_template("recruitment/detail.html", listing=listing, application_status=application_status)


# Profile edit. Pag pinalitan yung email, verify ulit at
# kailangan mag-sign in muli.
@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    form.user_id = current_user.id
    # Ipinasa ko yung lumang phone para hindi ma-validate yung
    # legacy value na hindi naman ginagalaw ng user.
    form.original_phone = current_user.phone or ""
    if current_user.role == "student" and request.method == "GET":
        form.year_level.data = current_user.student_profile.year_level
        form.campus.data = current_user.student_profile.campus
        form.facebook_url.data = current_user.student_profile.facebook_url
        form.bio.data = current_user.student_profile.bio
    if form.validate_on_submit():
        old_email = current_user.email
        current_user.full_name = form.full_name.data.strip()
        current_user.email = form.email.data.strip().lower()
        current_user.phone = form.phone.data.strip() or None
        if current_user.role == "student":
            profile = current_user.student_profile
            profile.year_level = form.year_level.data or None
            profile.campus = form.campus.data.strip() or None
            profile.facebook_url = form.facebook_url.data.strip() or None
            profile.bio = form.bio.data.strip() or None
        # Email change: verify ulit. Tinaasan ko auth_version at
        # nirevoke yung OTP para hindi na magamit sa lumang address.
        if current_user.email != old_email:
            current_user.email_verified = False
            current_user.auth_version += 1
            revoke_email_otps(current_user)
            audit_logger.email_changed(actor=current_user)
            user = current_user
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That email address was just claimed. Choose another address.", "error")
                return redirect(url_for("main.profile"))
            email = user.email
            logout_user()
            sent = issue_email_otp(user)
            db.session.commit()
            flash("Verify the new email address before signing in again." if sent else "Your email changed, but verification email delivery is unavailable. Use Resend code when email service is restored.", "info")
            return redirect(url_for("auth.verify_email", email=email))
        # Listahan ng fields na binago, hindi yung laman nila.
        audit_logger.profile_updated(actor=current_user, fields=["full_name", "phone", "email"] if current_user.role != "student" else ["full_name", "phone", "email", "year_level", "campus", "bio", "facebook_url"])
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That email address was just claimed. Choose another address.", "error")
            return redirect(url_for("main.profile"))
        flash("Your profile has been updated.", "success")
        return redirect(url_for("main.profile"))
    password_form = ChangePasswordForm()
    return render_template("profile.html", form=form, password_form=password_form,
                           max_avatar_size=MAX_PROFILE_IMAGE_SIZE)


# Upload ng avatar. Nasa upload.py yung size, format, at
# re-encode; dito lang yung role branch at flash.
@bp.route("/profile/avatar", methods=["POST"])
@login_required
def upload_avatar():
    if "avatar" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("main.profile"))

    file = request.files["avatar"]
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("main.profile"))

    old_filename = None
    if current_user.role == "patient":
        profile = current_user.patient_profile
        old_filename = profile.avatar_image
        success, error, filename = upload_patient_avatar(file, profile, old_filename)
        if not success:
            flash(error, "error")
            return redirect(url_for("main.profile"))
        profile.avatar_image = filename
    elif current_user.role == "student":
        profile = current_user.student_profile
        old_filename = profile.avatar_image
        success, error, filename = upload_student_avatar(file, profile, old_filename)
        if not success:
            flash(error, "error")
            return redirect(url_for("main.profile"))
        profile.avatar_image = filename
    else:
        flash("Admins cannot upload avatars.", "error")
        return redirect(url_for("main.profile"))

    audit_logger.avatar_uploaded(actor=current_user)
    db.session.commit()
    flash("Avatar updated.", "success")
    return redirect(url_for("main.profile"))


# Tanggal ng avatar. Yung file sa disk, binubura pagkatapos
# ng commit para hindi mawala yung record kung pumalya.
@bp.route("/profile/avatar/remove", methods=["POST"])
@login_required
def remove_avatar():
    if current_user.role == "patient":
        profile = current_user.patient_profile
        if profile.avatar_image:
            old_filename = profile.avatar_image
            profile.avatar_image = None
            db.session.commit()
            try:
                from ..upload import get_upload_root
                filepath = get_upload_root() / "avatars" / old_filename
                if filepath.exists():
                    filepath.unlink()
            except Exception:
                current_app.logger.warning(f"Failed to delete avatar file: {old_filename}")
            flash("Avatar removed.", "success")
        else:
            flash("No avatar to remove.", "info")
    elif current_user.role == "student":
        profile = current_user.student_profile
        if profile.avatar_image:
            old_filename = profile.avatar_image
            profile.avatar_image = None
            db.session.commit()
            try:
                from ..upload import get_upload_root
                filepath = get_upload_root() / "avatars" / old_filename
                if filepath.exists():
                    filepath.unlink()
            except Exception:
                current_app.logger.warning(f"Failed to delete avatar file: {old_filename}")
            flash("Avatar removed.", "success")
        else:
            flash("No avatar to remove.", "info")
    else:
        flash("Admins cannot remove avatars.", "error")

    audit_logger.avatar_removed(actor=current_user)
    db.session.commit()
    return redirect(url_for("main.profile"))


# Palit ng password. Kailangan tama yung current password,
# tapos logout para mag-sign in ulit.
@bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "error")
        else:
            current_user.set_password(form.password.data)
            current_user.auth_version += 1
            audit_logger.password_changed(actor=current_user)
            db.session.commit()
            logout_user()
            flash("Password changed successfully. Sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
    else:
        flash("Enter a valid new password and confirmation.", "error")
    return redirect(url_for("main.profile"))


# View ng ibang profile. Policy ang nagdedesisyon, tapos
# naka-log yung attempt kahit denied.
@bp.route("/profile/<int:user_id>")
@login_required
def view_profile(user_id):
    target_user = db.get_or_404(User, user_id)
    device = get_device_info(request)

    # Isang policy call lang, hindi na kailangang i-ulit yung
    # role checks dito sa route.
    result = ProfileAccessPolicy.can_view_profile(current_user, target_user)

    # Denied pero naka-log pa rin. Patient, 404 ang sagot para
    # hindi mabisto; student-to-student, 403.
    if result != AccessResult.ALLOWED:
        audit_logger.profile_viewed(viewer=current_user, target_user=target_user, allowed=False, device=device)
        db.session.commit()
        abort(404 if target_user.role == "patient" or result == AccessResult.NOT_FOUND else 403)

    if target_user.role == "student":
        visible_fields = ProfileAccessPolicy.get_visible_student_fields(current_user, target_user)
        audit_logger.profile_viewed(viewer=current_user, target_user=target_user, device=device)
        db.session.commit()
        return render_template("profile/view_student.html", student=target_user, fields=visible_fields)
    elif target_user.role == "patient":
        visible_fields = ProfileAccessPolicy.get_visible_patient_fields(current_user, target_user)
        audit_logger.profile_viewed(viewer=current_user, target_user=target_user, device=device)
        db.session.commit()
        return render_template("profile/view_patient.html", patient=target_user, fields=visible_fields)
    else:
        audit_logger.profile_viewed(viewer=current_user, target_user=target_user, device=device)
        db.session.commit()
        return render_template("profile/view_admin.html", admin=target_user)


# Mark as read. Sariling notification lang ang puwede.
@bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification(notification_id):
    from ..models import Notification, utcnow
    note = db.get_or_404(Notification, notification_id)
    if note.user_id != current_user.id:
        abort(403)
    note.read_at = utcnow()
    audit_logger.notification_read(actor=current_user, notification_id=note.id)
    db.session.commit()
    return redirect(request.referrer or url_for("main.dashboard"))


# Oras na lang ang hinihingi rito: naka-login lahat ng tao,
# kaya nasa policy pa rin yung tunay na check.
@bp.route("/uploads/avatars/<filename>")
@login_required
def serve_avatar(filename):
    user = None
    if current_user.role == "patient" and current_user.patient_profile and current_user.patient_profile.avatar_image == filename:
        user = current_user
    elif current_user.role == "student" and current_user.student_profile and current_user.student_profile.avatar_image == filename:
        user = current_user
    elif current_user.role == "admin":
        patient = db.session.scalar(db.select(Patient).where(Patient.avatar_image == filename))
        if patient:
            user = patient.user
        else:
            student = db.session.scalar(db.select(DentistryStudent).where(DentistryStudent.avatar_image == filename))
            if student:
                user = student.user
    else:
        patient = db.session.scalar(db.select(Patient).where(Patient.avatar_image == filename))
        if patient and can_view_patient_avatar(current_user, patient.user):
            user = patient.user
        else:
            student = db.session.scalar(db.select(DentistryStudent).where(DentistryStudent.avatar_image == filename))
            if student and can_view_student_avatar(current_user, student.user):
                user = student.user

    if not user:
        abort(404)

    filepath = get_avatar_path(user)
    if not filepath or not filepath.exists() or filepath.name != filename:
        abort(404)

    response = send_file(filepath, mimetype=_guess_mimetype(filename))
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# Cover images. Walang login requirement dito, kaya nasa
# can_view_listing_cover yung permission check.
@bp.route("/uploads/covers/<filename>")
def serve_cover(filename):
    listing = db.session.scalar(db.select(RecruitmentListing).where(RecruitmentListing.cover_image == filename))
    if not listing:
        abort(404)

    if not can_view_listing_cover(current_user, listing):
        abort(403)

    filepath = get_listing_cover_path(listing)
    if not filepath or not filepath.exists() or filepath.name != filename:
        abort(404)

    response = send_file(filepath, mimetype=_guess_mimetype(filename))
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# MIME type galing sa extension. Fixed map ito, hindi mula
# sa user input, para hindi ma-spoof yung header.
def _guess_mimetype(filename):
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")

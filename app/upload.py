import os
import secrets
import uuid
from pathlib import Path
from io import BytesIO
from functools import wraps
from flask import current_app, send_file, abort, request
from PIL import Image, UnidentifiedImageError
from .extensions import db
from .models import Patient, DentistryStudent, RecruitmentListing, User, utcnow

# Kung ilang bytes at pixels ang tinatanggap ko.
MAX_PROFILE_IMAGE_SIZE = 2 * 1024 * 1024
MAX_PROFILE_IMAGE_DIMENSION = 512
MAX_LISTING_IMAGE_SIZE = 4 * 1024 * 1024
MAX_LISTING_IMAGE_DIMENSION = 1600
# Allowed na type lang. Pero yung totoong check, sa
# content ng file, hindi sa header.
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

Image.MAX_IMAGE_PIXELS = 50_000_000


# Nasa instance folder, hindi sa static, para dumaan sa
# route na may permission check bago ma-serve.
def get_upload_root():
    root = current_app.config.get("UPLOAD_FOLDER")
    if not root:
        root = Path(current_app.instance_path) / "uploads"
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "avatars").mkdir(exist_ok=True)
    (root / "covers").mkdir(exist_ok=True)
    return root


# Returns (valid, error, image). Sinusubukan ko munang
# buksan, kaya file na peke ang extension, hindi papasa.
def validate_image_file(file_storage, max_size, max_dimension):
    # Size check bago pa buksan yung image para hindi
    # magastos sa memory.
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > max_size:
        return False, f"File size exceeds {max_size // (1024*1024)} MB limit.", None

    try:
        img = Image.open(file_storage)
        img.load()
        file_storage.seek(0)
    except UnidentifiedImageError:
        return False, "File is not a valid image.", None
    except Exception as e:
        return False, f"Image validation failed: {e}", None

    # JPEG, PNG, WebP lang. Yung format galing sa loob ng file,
    # hindi sa filename.
    if img.format not in {"JPEG", "PNG", "WEBP"}:
        return False, "Only JPEG, PNG, and WebP images are allowed.", None

    if img.width * img.height > Image.MAX_IMAGE_PIXELS:
        return False, "Image exceeds maximum pixel limit.", None

    return True, None, img


# Re-encode bago i-save. Yung bagong file, walang EXIF,
# kaya walang location data na sumasama.
def process_and_save_image(image, max_dimension, subfolder, old_filename=None):
    if image.mode in ("RGBA", "LA", "P"):
        pass

    # Resize lang kung sobra sa max dimension.
    if image.width > max_dimension or image.height > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    if image.format == "PNG":
        ext = ".png"
        fmt = "PNG"
        save_kwargs = {"optimize": True}
    elif image.format == "WEBP":
        ext = ".webp"
        fmt = "WEBP"
        save_kwargs = {"quality": 85, "method": 6}
    else:
        ext = ".jpg"
        fmt = "JPEG"
        save_kwargs = {"quality": 85, "optimize": True}
        if image.mode != "RGB":
            image = image.convert("RGB")

    # Random na filename, kaya hindi mahulaan yung URL at
    # walang laban kung may dalawang kaparehong pangalan.
    filename = f"{uuid.uuid4().hex}{ext}"

    upload_root = get_upload_root()
    filepath = upload_root / subfolder / filename

    image.save(filepath, fmt, **save_kwargs)

    # Pag napalitan, binubura ko yung lumang file. Naka-catch
    # yung error para hindi pumalya yung request.
    if old_filename:
        old_path = upload_root / subfolder / old_filename
        try:
            if old_path.exists():
                old_path.unlink()
        except Exception:
            current_app.logger.warning(f"Failed to delete old image: {old_path}")

    return filename


# Avatar ng patient. Returns (ok, error, filename).
def upload_patient_avatar(file_storage, patient, old_filename=None):
    valid, error, img = validate_image_file(file_storage, MAX_PROFILE_IMAGE_SIZE, MAX_PROFILE_IMAGE_DIMENSION)
    if not valid:
        return False, error, None

    filename = process_and_save_image(img, MAX_PROFILE_IMAGE_DIMENSION, "avatars", old_filename)
    return True, None, filename


# Kapareho ng patient avatar, 2 MB at 512 px limit.
def upload_student_avatar(file_storage, student, old_filename=None):
    valid, error, img = validate_image_file(file_storage, MAX_PROFILE_IMAGE_SIZE, MAX_PROFILE_IMAGE_DIMENSION)
    if not valid:
        return False, error, None

    filename = process_and_save_image(img, MAX_PROFILE_IMAGE_DIMENSION, "avatars", old_filename)
    return True, None, filename


# Cover ng listing, mas malaki ang allowed: 4 MB at 1600 px.
def upload_listing_cover(file_storage, listing, old_filename=None):
    valid, error, img = validate_image_file(file_storage, MAX_LISTING_IMAGE_SIZE, MAX_LISTING_IMAGE_DIMENSION)
    if not valid:
        return False, error, None

    filename = process_and_save_image(img, MAX_LISTING_IMAGE_DIMENSION, "covers", old_filename)
    return True, None, filename


# Iba yung table ng patient at student, kaya naka-branch
# dito yung path ng avatar.
def get_avatar_path(user):
    if user.role == "patient" and user.patient_profile and user.patient_profile.avatar_image:
        return get_upload_root() / "avatars" / user.patient_profile.avatar_image
    elif user.role == "student" and user.student_profile and user.student_profile.avatar_image:
        return get_upload_root() / "avatars" / user.student_profile.avatar_image
    return None


# Path ng cover sa loob ng uploads folder.
def get_listing_cover_path(listing):
    if listing.cover_image:
        return get_upload_root() / "covers" / listing.cover_image
    return None


# Hindi kalayaan ito: sinusundan ko yung policy ng patient
# profile, plus yung owner ng avatar.
def can_view_patient_avatar(viewer, patient_user):
    from .profile_policy import AccessResult, ProfileAccessPolicy

    if viewer.is_authenticated and viewer.id == patient_user.id:
        return True
    return ProfileAccessPolicy.can_view_patient_profile(viewer, patient_user) == AccessResult.ALLOWED


# Student avatar, kaparehong rule sa student profile page.
def can_view_student_avatar(viewer, student_user):
    from .profile_policy import AccessResult, ProfileAccessPolicy

    if viewer.is_authenticated and viewer.id == student_user.id:
        return True
    return ProfileAccessPolicy.can_view_student_profile(viewer, student_user) == AccessResult.ALLOWED


# Published covers, public. Yung draft o closed, owner at
# admin lang. Pending student, hindi pa maaabot.
def can_view_listing_cover(viewer, listing):
    if viewer.is_authenticated:
        if viewer.role == "admin":
            return True
        if viewer.role == "student" and viewer.student_profile and listing.student_id == viewer.student_profile.id:
            return True
    if (
        listing.status == "published"
        and listing.student.user.is_active
        and listing.student.user.approval_status == "approved"
    ):
        return True
    return False
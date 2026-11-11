"""Secure image upload and serving for NU DentalConnect."""
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

# Configuration defaults
MAX_PROFILE_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_PROFILE_IMAGE_DIMENSION = 512
MAX_LISTING_IMAGE_SIZE = 4 * 1024 * 1024  # 4 MB
MAX_LISTING_IMAGE_DIMENSION = 1600
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Set decompression bomb limit
Image.MAX_IMAGE_PIXELS = 50_000_000  # 50 megapixels


def get_upload_root():
    """Get the root directory for uploads (outside static)."""
    root = current_app.config.get("UPLOAD_FOLDER")
    if not root:
        root = Path(current_app.instance_path) / "uploads"
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Create subdirectories
    (root / "avatars").mkdir(exist_ok=True)
    (root / "covers").mkdir(exist_ok=True)
    return root


def validate_image_file(file_storage, max_size, max_dimension):
    """
    Validate an uploaded image file.
    Returns (is_valid, error_message, image_object).
    """
    # Check file size
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > max_size:
        return False, f"File size exceeds {max_size // (1024*1024)} MB limit.", None

    # Check MIME type via content sniffing (not header)
    try:
        img = Image.open(file_storage)
        img.load()  # Force load to detect corruption
        file_storage.seek(0)
    except UnidentifiedImageError:
        return False, "File is not a valid image.", None
    except Exception as e:
        return False, f"Image validation failed: {e}", None

    # Check format
    if img.format not in {"JPEG", "PNG", "WEBP"}:
        return False, "Only JPEG, PNG, and WebP images are allowed.", None

    # Check total pixels (decompression bomb protection)
    if img.width * img.height > Image.MAX_IMAGE_PIXELS:
        return False, "Image exceeds maximum pixel limit.", None

    return True, None, img


def process_and_save_image(image, max_dimension, subfolder, old_filename=None):
    """
    Process image: re-encode, strip EXIF, save with UUID filename.
    Returns the new filename.
    """
    # Convert to RGB if necessary (for JPEG output)
    if image.mode in ("RGBA", "LA", "P"):
        # Keep transparency for PNG/WebP, but convert for JPEG
        pass

    # Resize if needed
    if image.width > max_dimension or image.height > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    # Generate UUID filename with appropriate extension
    # Preserve original format if it's PNG/WebP, else use JPEG
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
        # Convert to RGB for JPEG
        if image.mode != "RGB":
            image = image.convert("RGB")

    filename = f"{uuid.uuid4().hex}{ext}"

    upload_root = get_upload_root()
    filepath = upload_root / subfolder / filename

    # Save processed image
    image.save(filepath, fmt, **save_kwargs)

    # Delete old file if exists
    if old_filename:
        old_path = upload_root / subfolder / old_filename
        try:
            if old_path.exists():
                old_path.unlink()
        except Exception:
            current_app.logger.warning(f"Failed to delete old image: {old_path}")

    return filename


def upload_patient_avatar(file_storage, patient, old_filename=None):
    """Upload and process patient avatar."""
    valid, error, img = validate_image_file(file_storage, MAX_PROFILE_IMAGE_SIZE, MAX_PROFILE_IMAGE_DIMENSION)
    if not valid:
        return False, error, None

    filename = process_and_save_image(img, MAX_PROFILE_IMAGE_DIMENSION, "avatars", old_filename)
    return True, None, filename


def upload_student_avatar(file_storage, student, old_filename=None):
    """Upload and process student avatar."""
    valid, error, img = validate_image_file(file_storage, MAX_PROFILE_IMAGE_SIZE, MAX_PROFILE_IMAGE_DIMENSION)
    if not valid:
        return False, error, None

    filename = process_and_save_image(img, MAX_PROFILE_IMAGE_DIMENSION, "avatars", old_filename)
    return True, None, filename


def upload_listing_cover(file_storage, listing, old_filename=None):
    """Upload and process listing cover image."""
    valid, error, img = validate_image_file(file_storage, MAX_LISTING_IMAGE_SIZE, MAX_LISTING_IMAGE_DIMENSION)
    if not valid:
        return False, error, None

    filename = process_and_save_image(img, MAX_LISTING_IMAGE_DIMENSION, "covers", old_filename)
    return True, None, filename


def get_avatar_path(user):
    """Get the avatar image path for a user (patient or student)."""
    if user.role == "patient" and user.patient_profile and user.patient_profile.avatar_image:
        return get_upload_root() / "avatars" / user.patient_profile.avatar_image
    elif user.role == "student" and user.student_profile and user.student_profile.avatar_image:
        return get_upload_root() / "avatars" / user.student_profile.avatar_image
    return None


def get_listing_cover_path(listing):
    """Get the cover image path for a listing."""
    if listing.cover_image:
        return get_upload_root() / "covers" / listing.cover_image
    return None


def can_view_patient_avatar(viewer, patient_user):
    """Delegate to the same policy that protects the patient profile page."""
    from .profile_policy import AccessResult, ProfileAccessPolicy

    if viewer.is_authenticated and viewer.id == patient_user.id:
        return True
    return ProfileAccessPolicy.can_view_patient_profile(viewer, patient_user) == AccessResult.ALLOWED


def can_view_student_avatar(viewer, student_user):
    """Student avatars follow the student profile rule, not "any signed-in user"."""
    from .profile_policy import AccessResult, ProfileAccessPolicy

    if viewer.is_authenticated and viewer.id == student_user.id:
        return True
    return ProfileAccessPolicy.can_view_student_profile(viewer, student_user) == AccessResult.ALLOWED


def can_view_listing_cover(viewer, listing):
    """Published covers are public; unpublished covers are owner/admin only."""
    if viewer.is_authenticated:
        if viewer.role == "admin":
            return True
        if viewer.role == "student" and viewer.student_profile and listing.student_id == viewer.student_profile.id:
            return True
    # A pending or deactivated student's listing must not be reachable by URL.
    if (
        listing.status == "published"
        and listing.student.user.is_active
        and listing.student.user.approval_status == "approved"
    ):
        return True
    return False
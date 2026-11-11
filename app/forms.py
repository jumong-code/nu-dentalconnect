from flask_wtf import FlaskForm
import re
from datetime import timezone
from urllib.parse import urlparse
from wtforms import BooleanField, EmailField, HiddenField, StringField, PasswordField, SelectField, TextAreaField, DateTimeLocalField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError
from .models import User, utcnow
from .time_utils import MANILA_TZ
from .formatters import FieldFormatter


def clean_text(value):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value or "").strip()


# Phone policy (single definition, mirrored in app.js VALIDATION_RULES):
# at most 20 characters, 7-15 digits, only digits and "-", "+" only first,
# and no consecutive hyphens.
PHONE_MAX_LENGTH = 20
PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15
PHONE_PATTERN = r"^\+?[0-9](?:-?[0-9])*$"


def validate_phone_value(form, field):
    value = clean_text(field.data)
    if not value:
        return
    digits = re.sub(r"\D", "", value)
    if (
        len(value) > PHONE_MAX_LENGTH
        or "--" in value
        or not re.fullmatch(PHONE_PATTERN, value)
        or not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS
    ):
        raise ValidationError(
            "Enter a phone number with 7 to 15 digits, no more than 20 characters, "
            "using only numbers and hyphens (with + only at the start)."
        )


def validate_profile_phone(form, field):
    """Profile-only phone rule that tolerates an unchanged legacy value.

    The route sets ``form.original_phone`` before ``validate_on_submit()``. A
    legacy value saved under the old, looser rule is accepted while untouched
    and validated as soon as the user edits it.
    """
    if getattr(form, "original_phone", None) is not None and (field.data or "") == form.original_phone:
        return
    validate_phone_value(form, field)


def validate_name_value(form, field):
    if not re.fullmatch(r"[\w][\w .,'’\-]{0,118}[\w.]?", clean_text(field.data), re.UNICODE):
        raise ValidationError("Use letters, spaces, apostrophes, periods, or hyphens in the name.")


def validate_password_strength(form, field):
    value = field.data or ""
    if not (re.search(r"[a-z]", value) and re.search(r"[A-Z]", value) and re.search(r"\d", value)):
        raise ValidationError("Use at least one uppercase letter, one lowercase letter, and one number.")


def validate_year_level(form, field):
    """Validate and format year level using FieldFormatter."""
    if field.data:
        formatted = FieldFormatter.format_year_level(field.data)
        if formatted is None:
            raise ValidationError("Enter Year 1 to Year 5 or Intern.")
        field.data = formatted


def validate_campus(form, field):
    """Validate and format campus using FieldFormatter."""
    if field.data:
        formatted = FieldFormatter.format_campus(field.data)
        if formatted is None:
            raise ValidationError("Enter a valid campus name.")
        field.data = formatted


YEAR_LEVEL_CHOICES = [
    ("", "Select year level"),
    ("Year 1", "Year 1"),
    ("Year 2", "Year 2"),
    ("Year 3", "Year 3"),
    ("Year 4", "Year 4"),
    ("Year 5", "Year 5"),
    ("Intern", "Intern"),
]


class RegisterForm(FlaskForm):
    full_name = StringField("Full name", filters=[clean_text], validators=[DataRequired(), Length(min=2, max=120), validate_name_value])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField("I am a", choices=[("patient", "Patient"), ("student", "Dentistry student")], validators=[DataRequired()])
    phone = StringField("Phone number", filters=[clean_text], validators=[DataRequired(), Length(max=PHONE_MAX_LENGTH), validate_phone_value], render_kw={"maxlength": str(PHONE_MAX_LENGTH), "inputmode": "tel", "pattern": "\\+?[0-9](?:-?[0-9])*"})
    # Optional starter details for student accounts. Year level is a fixed
    # dropdown; campus is still normalised by FieldFormatter.
    year_level = SelectField(
        "Year level (students)",
        choices=YEAR_LEVEL_CHOICES,
        default="",
        validators=[Optional(), validate_year_level],
    )
    campus = StringField("Campus (students)", filters=[clean_text], validators=[Optional(), Length(max=120), validate_campus], render_kw={"maxlength": "120", "placeholder": "e.g. NU Manila"})
    password = PasswordField("Password", validators=[DataRequired(), Length(min=12, max=128), validate_password_strength])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), Length(max=128), EqualTo("password")])
    submit = SubmitField("Create account")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("An account with this email already exists.")


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    submit = SubmitField("Sign in")


class ResetRequestForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send reset link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128), validate_password_strength])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), Length(max=128), EqualTo("password")])
    submit = SubmitField("Update password")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired(), Length(max=128)])
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128), validate_password_strength])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), Length(max=128), EqualTo("password")])
    submit = SubmitField("Change password")


class ProfileForm(FlaskForm):
    full_name = StringField("Full name", filters=[clean_text], validators=[DataRequired(), Length(min=2, max=120), validate_name_value])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = StringField("Phone", filters=[clean_text], validators=[Optional(), Length(max=PHONE_MAX_LENGTH), validate_profile_phone], render_kw={"maxlength": str(PHONE_MAX_LENGTH), "inputmode": "tel", "pattern": "\\+?[0-9](?:-?[0-9])*"})
    year_level = StringField("Year level", filters=[clean_text], validators=[Optional(), Length(max=80), validate_year_level], render_kw={"maxlength": "80"})
    campus = StringField("Campus", filters=[clean_text], validators=[Optional(), Length(max=120), validate_campus], render_kw={"maxlength": "120"})
    facebook_url = StringField("Facebook profile or page", filters=[clean_text], validators=[Optional(), Length(max=255)], render_kw={"maxlength": "255"})
    bio = TextAreaField("About your practice", filters=[clean_text], validators=[Optional(), Length(max=500)], render_kw={"maxlength": "500"})
    submit = SubmitField("Save profile")

    def validate_email(self, field):
        existing = User.query.filter_by(email=field.data.strip().lower()).first()
        if existing and existing.id != self.user_id:
            raise ValidationError("That email address is already in use.")

    def validate_facebook_url(self, field):
        value = field.data or ""
        if not value:
            return
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"facebook.com", "www.facebook.com", "m.facebook.com"} or not parsed.path.strip("/"):
            raise ValidationError("Enter a full https://www.facebook.com/ profile or page URL.")


class ListingForm(FlaskForm):
    submission_key = HiddenField(validators=[DataRequired(), Length(min=32, max=64)])
    publish_now = BooleanField("Publish this listing immediately")
    template_name = StringField("Save these fields as a template (optional)", filters=[clean_text], validators=[Optional(), Length(max=80)])
    title = StringField("Listing title", filters=[clean_text], validators=[DataRequired(), Length(min=3, max=50)])
    category = StringField("Procedure category", filters=[clean_text], validators=[DataRequired(), Length(min=2, max=100)])
    location = StringField("Location", filters=[clean_text], validators=[DataRequired(), Length(min=3, max=180), Regexp(r"^[\w .,'’()\-/#]*$", message="Enter a plain-text location.")])
    preferred_schedule = StringField("Preferred appointment schedule", filters=[clean_text], validators=[DataRequired(), Length(min=3, max=180)])
    description = TextAreaField("Procedure details", filters=[clean_text], validators=[DataRequired(), Length(min=20, max=5000)])
    eligibility = TextAreaField("Who can request this appointment?", filters=[clean_text], validators=[DataRequired(), Length(min=5, max=2000)])
    submit = SubmitField("Save appointment listing")


class ApplicationForm(FlaskForm):
    message = TextAreaField("Message to the student", filters=[clean_text], validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Send patient application")


class AppointmentForm(FlaskForm):
    starts_at = DateTimeLocalField("Requested date and time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    note = TextAreaField("Note", filters=[clean_text], validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Request appointment")

    def validate_starts_at(self, field):
        if field.data:
            starts_at_utc = field.data.replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            if starts_at_utc <= utcnow():
                raise ValidationError("Choose a future date and time.")
            field.data = starts_at_utc


class ScheduleForm(FlaskForm):
    proposed_at = DateTimeLocalField("Alternative date and time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    submit = SubmitField("Propose time")

    def validate_proposed_at(self, field):
        if field.data:
            proposed_at_utc = field.data.replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            if proposed_at_utc <= utcnow():
                raise ValidationError("Choose a future date and time.")
            field.data = proposed_at_utc


class VerifyOTPForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    code = StringField("Six-digit code", validators=[DataRequired(), Length(min=6, max=6), Regexp(r"^\d{6}$", message="Enter the six-digit code from your email.")], render_kw={"maxlength": "6", "inputmode": "numeric", "pattern": "[0-9]{6}"})
    submit = SubmitField("Verify email")


class ResendOTPForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Resend code")


class ResumeVerificationForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send verification code")


class StatusForm(FlaskForm):
    submit = SubmitField("Save")


class AdminSetPasswordForm(FlaskForm):
    """Form for admins to set/reset password for non-admin users."""
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128), validate_password_strength])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), Length(max=128), EqualTo("password")])
    submit = SubmitField("Set password")

# Forms at validation. Dito yung server-side check. Yung
# app.js mirror lang para mabilis makita yung error sa browser.
from flask_wtf import FlaskForm
import re
from datetime import timezone
from urllib.parse import urlparse
from wtforms import BooleanField, EmailField, HiddenField, StringField, PasswordField, SelectField, TextAreaField, DateTimeLocalField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError
from .models import User, utcnow
from .time_utils import MANILA_TZ
from .formatters import FieldFormatter


# Tinatanggal yung control characters at extra spaces bago
# pumasok sa database. Ginagamit ito sa filters ng Field.
def clean_text(value):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value or "").strip()


# Isang definition lang ng phone rule. Yung app.js may pareho
# para makapag-validate agad habang nagta-type.
PHONE_MAX_LENGTH = 20
PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15
PHONE_PATTERN = r"^\+?[0-9](?:-?[0-9])*$"


# Bilang ng digits ang tinitignan ko, hindi lang haba.
# Bawal din yung sunod-sunod na hyphen.
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


# Exception sa profile: kung hindi ginalaw yung lumang number,
# papasa muna, para hindi masira yung existing data.
def validate_profile_phone(form, field):
    if getattr(form, "original_phone", None) is not None and (field.data or "") == form.original_phone:
        return
    validate_phone_value(form, field)


# Letters, spaces, apostrophe, period, hyphen lang. Yung
# unicode flag para kasya pati curly apostrophe.
def validate_name_value(form, field):
    if not re.fullmatch(r"[\w][\w .,'’\-]{0,118}[\w.]?", clean_text(field.data), re.UNICODE):
        raise ValidationError("Use letters, spaces, apostrophes, periods, or hyphens in the name.")


# Kailangan may lowercase, uppercase, at number. Server side
# ito, kaya hindi basta nakadepende sa JS sa browser.
def validate_password_strength(form, field):
    value = field.data or ""
    if not (re.search(r"[a-z]", value) and re.search(r"[A-Z]", value) and re.search(r"\d", value)):
        raise ValidationError("Use at least one uppercase letter, one lowercase letter, and one number.")


# Hinihingi ko yung format sa FieldFormatter. Pag walang
# tugma, error, para hindi kalat yung format sa database.
def validate_year_level(form, field):
    if field.data:
        formatted = FieldFormatter.format_year_level(field.data)
        if formatted is None:
            raise ValidationError("Enter Year 1 to Year 5 or Intern.")
        field.data = formatted


# Pareho sa year level: linisin at i-format muna bago i-save.
def validate_campus(form, field):
    if field.data:
        formatted = FieldFormatter.format_campus(field.data)
        if formatted is None:
            raise ValidationError("Enter a valid campus name.")
        field.data = formatted


# Fixed na choices ito sa registration. Sa profile text field,
# kaya doon kailangan ng formatter.
YEAR_LEVEL_CHOICES = [
    ("", "Select year level"),
    ("Year 1", "Year 1"),
    ("Year 2", "Year 2"),
    ("Year 3", "Year 3"),
    ("Year 4", "Year 4"),
    ("Year 5", "Year 5"),
    ("Intern", "Intern"),
]


# Registration form. Server pa rin ang final check kahit may
# HTML validation at app.js na tumutulong sa browser.
class RegisterForm(FlaskForm):
    full_name = StringField("Full name", filters=[clean_text], validators=[DataRequired(), Length(min=2, max=120), validate_name_value])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField("I am a", choices=[("patient", "Patient"), ("student", "Dentistry student")], validators=[DataRequired()])
    phone = StringField("Phone number", filters=[clean_text], validators=[DataRequired(), Length(max=PHONE_MAX_LENGTH), validate_phone_value], render_kw={"maxlength": str(PHONE_MAX_LENGTH), "inputmode": "tel", "pattern": "\\+?[0-9](?:-?[0-9])*"})
    # Sa registration dropdown ito, pero text field sa profile.
    # Parehong dadaan sa validate_year_level.
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

    # Dito kinukuha yung duplicate email. Dapat sa server talaga
    # kasi puwedeng i-bypass yung validation sa browser.
    def validate_email(self, field):
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("An account with this email already exists.")


# Simpleng login form. Yung password check, sa route.
class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    submit = SubmitField("Sign in")


# Forgot password: email lang ang hihingin.
class ResetRequestForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send reset link")


# Bagong password galing sa reset link.
class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128), validate_password_strength])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), Length(max=128), EqualTo("password")])
    submit = SubmitField("Update password")


# Palit ng password habang naka-login, kaya kailangan
# yung current password.
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired(), Length(max=128)])
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128), validate_password_strength])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), Length(max=128), EqualTo("password")])
    submit = SubmitField("Change password")


# Profile form. Students may extra fields, patients wala.
# Yung user_id ang gamit para hindi i-flag yung sariling email.
class ProfileForm(FlaskForm):
    full_name = StringField("Full name", filters=[clean_text], validators=[DataRequired(), Length(min=2, max=120), validate_name_value])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = StringField("Phone", filters=[clean_text], validators=[Optional(), Length(max=PHONE_MAX_LENGTH), validate_profile_phone], render_kw={"maxlength": str(PHONE_MAX_LENGTH), "inputmode": "tel", "pattern": "\\+?[0-9](?:-?[0-9])*"})
    year_level = StringField("Year level", filters=[clean_text], validators=[Optional(), Length(max=80), validate_year_level], render_kw={"maxlength": "80"})
    campus = StringField("Campus", filters=[clean_text], validators=[Optional(), Length(max=120), validate_campus], render_kw={"maxlength": "120"})
    facebook_url = StringField("Facebook profile or page", filters=[clean_text], validators=[Optional(), Length(max=255)], render_kw={"maxlength": "255"})
    bio = TextAreaField("About your practice", filters=[clean_text], validators=[Optional(), Length(max=500)], render_kw={"maxlength": "500"})
    submit = SubmitField("Save profile")

    # Pag ibang account na may parehong email, error. Kung
    # sarili niya, ok lang.
    def validate_email(self, field):
        existing = User.query.filter_by(email=field.data.strip().lower()).first()
        if existing and existing.id != self.user_id:
            raise ValidationError("That email address is already in use.")

    # https at facebook.com lang, tapos may path. Ayaw ko
    # mag-imbak ng kung saan-saang link sa profile.
    def validate_facebook_url(self, field):
        value = field.data or ""
        if not value:
            return
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"facebook.com", "www.facebook.com", "m.facebook.com"} or not parsed.path.strip("/"):
            raise ValidationError("Enter a full https://www.facebook.com/ profile or page URL.")


# Listing form ng student. Yung submission_key na hidden
# field ang pumipigil sa doble pag-click ng Save.
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


# Application message. Optional ito at hindi booking.
class ApplicationForm(FlaskForm):
    message = TextAreaField("Message to the student", filters=[clean_text], validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Send patient application")


# Appointment request. datetime-local galing sa browser,
# Manila time ang assumption ko sa input.
class AppointmentForm(FlaskForm):
    starts_at = DateTimeLocalField("Requested date and time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    note = TextAreaField("Note", filters=[clean_text], validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Request appointment")

    # Manila time yung pinasok, kaya iko-convert ko muna sa UTC
    # bago i-save at bago i-compare sa utcnow().
    def validate_starts_at(self, field):
        if field.data:
            starts_at_utc = field.data.replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            if starts_at_utc <= utcnow():
                raise ValidationError("Choose a future date and time.")
            field.data = starts_at_utc


# Form para sa pag-propose ng bagong oras.
class ScheduleForm(FlaskForm):
    proposed_at = DateTimeLocalField("Alternative date and time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    submit = SubmitField("Propose time")

    # Pareho sa appointment: Manila time papasok, UTC ang
    # itatabi sa database.
    def validate_proposed_at(self, field):
        if field.data:
            proposed_at_utc = field.data.replace(tzinfo=MANILA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
            if proposed_at_utc <= utcnow():
                raise ValidationError("Choose a future date and time.")
            field.data = proposed_at_utc


# 6 digits lang, may pattern. Pero yung totoong check ng
# code, nasa verify_email_otp sa services.
class VerifyOTPForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    code = StringField("Six-digit code", validators=[DataRequired(), Length(min=6, max=6), Regexp(r"^\d{6}$", message="Enter the six-digit code from your email.")], render_kw={"maxlength": "6", "inputmode": "numeric", "pattern": "[0-9]{6}"})
    submit = SubmitField("Verify email")


# Resend ng code. Generic ang sagot sa route para hindi
# malaman kung may account.
class ResendOTPForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Resend code")


# Para sa nag-register pero hindi natapos yung verification.
class ResumeVerificationForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send verification code")


# Submit button lang ito. Nandito para may CSRF token pa rin
# yung maliliit na status change.
class StatusForm(FlaskForm):
    submit = SubmitField("Save")


# Admin lang ang puwedeng gumamit. Hindi kasama yung admin
# accounts, nasa route yung check.
class AdminSetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128), validate_password_strength])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), Length(max=128), EqualTo("password")])
    submit = SubmitField("Set password")

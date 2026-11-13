# Dito ginagawa yung Flask app. Factory pattern para hindi
# global yung app object.
from datetime import datetime, timezone
from flask import Flask, render_template
from config import Config
from .extensions import csrf, db, login_manager, mail, migrate
from .time_utils import MANILA_TZ


# Lahat ng setup dito: config, extensions, blueprint, errors.
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Tawagin yung Config.validate() bago pa magsimula yung app.
    validate_config = getattr(config_class, "validate", None)
    if validate_config:
        validate_config()
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    # SMTP (Flask-Mail) at CSRF protection ng Flask-WTF.
    mail.init_app(app)
    csrf.init_app(app)

    # Pagkatapos ng bawat response, chine-check kung may device
    # cookie na. Kung wala, nilalagyan ng bago. Random value lang
    # sa browser; sa audit, hash lang, hindi yung raw value.
    @app.after_request
    def identify_device(response):
        from .audit import DeviceInfo

        device = DeviceInfo.from_request()
        if device.device_id is None:
            device.set_cookie(response, secure=app.config.get("SESSION_COOKIE_SECURE", False))
        return response

    # Filter para sa template. UTC yung nasa DB, Manila time
    # yung ipinapakita sa user.
    @app.template_filter("local_datetime")
    def local_datetime(value, format_string="%b %d, %Y %I:%M %p"):
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(MANILA_TZ).strftime(format_string)

    # Security headers: nosniff, DENY sa frame, referrer policy,
    # at HSTS pag naka-secure yung cookie.
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    # Nasa loob na ng function yung imports para iwas circular import.
    from . import models
    from .routes import auth, main, patient, student, admin
    # Lima yung blueprint. Yung auth, patient, student, at admin
    # may url_prefix para malinaw kung saan naka-mount.
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp, url_prefix="/auth")
    app.register_blueprint(patient.bp, url_prefix="/patient")
    app.register_blueprint(student.bp, url_prefix="/student")
    app.register_blueprint(admin.bp, url_prefix="/admin")

    # CLI command: flask create-admin. Yung docstring sa baba
    # ginagamit ni Click bilang --help text, kaya hindi ko tinanggal.
    @app.cli.command("create-admin")
    def create_admin():
        """Create an administrator account interactively for the local installation."""
        import getpass
        import re
        from email_validator import EmailNotValidError, validate_email
        from .models import User
        from .services import record_audit
        name = input("Administrator name: ").strip()
        email_input = input("Administrator email: ").strip()
        password = getpass.getpass("Password (12+ characters, upper/lowercase and number): ")
        try:
            email = validate_email(email_input, check_deliverability=False).normalized.lower()
        except EmailNotValidError as error:
            raise SystemExit("Enter a valid administrator email address.") from error
        if len(name) < 2 or len(name) > 120 or len(password) < 12 or not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password) and re.search(r"\d", password)) or User.query.filter_by(email=email).first():
            raise SystemExit("Check the administrator name, password policy, and email uniqueness.")
        user = User(full_name=name, email=email, role="admin", email_verified=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        record_audit("admin_bootstrap", "user", user.id, {"role": "admin"}, actor=user)
        db.session.commit()
        print("Administrator created.")

    # Custom error pages para hindi lumabas yung default HTML.
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    # Pag 404, ito yung template na ipapakita.
    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    return app

import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    APP_ENV = os.getenv("APP_ENV", "development").lower()
    SECRET_KEY = os.getenv("SECRET_KEY") or (secrets.token_hex(32) if APP_ENV != "production" else None)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "mysql+pymysql://root:password@localhost/dentalconnect?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "dentalconnect_session"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true" if APP_ENV == "production" else "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = APP_ENV == "production"
    MAX_CONTENT_LENGTH = 5_242_880  # 5 MB (allows 4 MB file + form overhead)
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "NU DentalConnect <noreply@example.com>")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000")
    # Single source of truth for campus authorization wording. The authorizing
    # office is intentionally a placeholder until the client supplies it.
    AUTHORIZATION_NOTICE = os.getenv(
        "AUTHORIZATION_NOTICE",
        "[INSERT AUTHORIZING OFFICE] has authorized this project for campus use.",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    @classmethod
    def validate(cls):
        if cls.MAIL_USE_TLS and cls.MAIL_USE_SSL:
            raise RuntimeError("Configure either SMTP TLS or SMTP SSL, not both.")
        if cls.APP_ENV == "production":
            required = {
                "SECRET_KEY": cls.SECRET_KEY,
                "DATABASE_URL": os.getenv("DATABASE_URL"),
                "MAIL_SERVER": cls.MAIL_SERVER,
                "MAIL_PORT": os.getenv("MAIL_PORT"),
                "MAIL_USERNAME": cls.MAIL_USERNAME,
                "MAIL_PASSWORD": cls.MAIL_PASSWORD,
                "MAIL_DEFAULT_SENDER": os.getenv("MAIL_DEFAULT_SENDER"),
            }
            missing = [key for key, value in required.items() if not value]
            if missing:
                raise RuntimeError("Production configuration missing: " + ", ".join(missing))
            if len(cls.SECRET_KEY) < 32:
                raise RuntimeError("Production SECRET_KEY must contain at least 32 characters.")
            if not cls.SQLALCHEMY_DATABASE_URI.startswith("mysql+"):
                raise RuntimeError("Production DATABASE_URL must use a MySQL SQLAlchemy driver URL.")
            if not cls.APP_BASE_URL.startswith("https://"):
                raise RuntimeError("Production APP_BASE_URL must use HTTPS.")
            if not cls.SESSION_COOKIE_SECURE:
                raise RuntimeError("Production COOKIE_SECURE must be true.")
            if not (cls.MAIL_USE_TLS or cls.MAIL_USE_SSL):
                raise RuntimeError("Production SMTP must use TLS or SSL.")

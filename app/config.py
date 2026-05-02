import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Database ───────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI      = os.getenv('DATABASE_URL', 'sqlite:///diagnovate.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── JWT ────────────────────────────────────────────────────
    JWT_SECRET_KEY         = os.getenv('JWT_SECRET_KEY', 'super-secret-key-change-in-production')
    # FIX: must be timedelta, NOT an int (seconds caused silent bugs with flask-jwt-extended)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)

    # ── Flask ──────────────────────────────────────────────────
    SECRET_KEY = os.getenv('SECRET_KEY', 'flask-secret-key-change-in-production')
    DEBUG      = os.getenv('DEBUG', 'True') == 'True'
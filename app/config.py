# NOTE: هذا الملف غير مستخدم حالياً - الـ configuration موجود في app/__init__.py
# تم الإبقاء عليه للمرجعية فقط

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///diagnovate.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT - 30 دقيقة (يطابق __init__.py)
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'super-secret-key-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = 30 * 60  # 30 minutes in seconds

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'flask-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False') == 'True'
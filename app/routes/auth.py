from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from datetime import timedelta
import os
import re

auth_bp = Blueprint('auth', __name__)

DEV_MODE    = os.getenv("DEV_MODE", "false").lower() == "true"
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
SERVICE_SID = os.getenv("TWILIO_SERVICE_SID")

# FIX: only instantiate Twilio client when NOT in DEV_MODE
# Prevents crash on startup when credentials are missing
twilio_client = None
if not DEV_MODE:
    try:
        from twilio.rest import Client
        twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)
        print("✅ Twilio client loaded")
    except Exception as e:
        print(f"⚠️ Twilio init failed: {e}")


def validate_email(email: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))


def validate_phone(phone: str) -> bool:
    return bool(re.match(r'^(\+966|05)\d{8}$', phone))


# ── SIGNUP ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        name     = (data.get('name') or '').strip()
        email    = (data.get('email') or '').strip()
        phone    = (data.get('phone') or '').strip()
        password = (data.get('password') or '').strip()

        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        if not phone:
            return jsonify({'error': 'Phone is required'}), 400
        if not password or len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        if not validate_phone(phone):
            return jsonify({'error': 'Invalid phone format. Use +966XXXXXXXX or 05XXXXXXXX'}), 400

        if Doctor.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 409
        if Doctor.query.filter_by(phone=phone).first():
            return jsonify({'error': 'Phone already registered'}), 409

        doctor = Doctor(
            name           = name,
            email          = email,
            phone          = phone,
            specialty      = data.get('specialty', 'Thyroid Specialist'),
            license_number = data.get('license_number', ''),
            status         = 'pending',
        )
        doctor.set_password(password)
        db.session.add(doctor)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Account created successfully. Awaiting admin approval.',
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"ERROR in signup: {e}")
        return jsonify({'error': str(e)}), 500


# ── LOGIN ──────────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        identifier = (data.get('identifier') or '').strip()
        password   = (data.get('password') or '').strip()

        if not identifier:
            return jsonify({'error': 'Email is required'}), 400
        if not password:
            return jsonify({'error': 'Password is required'}), 400

        doctor = Doctor.query.filter_by(email=identifier).first()
        if not doctor or not doctor.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401

        if doctor.status == 'pending':
            return jsonify({'error': 'Your account is pending admin approval.'}), 403
        if doctor.status == 'inactive':
            return jsonify({'error': 'Your account has been deactivated. Contact admin.'}), 403

        # ── DEV MODE: skip OTP ─────────────────────────────────
        if DEV_MODE:
            print("⚠️  DEV_MODE ON — skipping OTP")
            access_token = create_access_token(
                identity=str(doctor.id),
                expires_delta=timedelta(days=7)
            )
            return jsonify({
                'success':      True,
                'access_token': access_token,
                'doctor': {
                    'id':        doctor.id,
                    'name':      doctor.name,
                    'email':     doctor.email,
                    'phone':     doctor.phone,
                    'specialty': doctor.specialty,
                }
            }), 200

        # ── PRODUCTION: send OTP ───────────────────────────────
        if not twilio_client:
            return jsonify({'error': 'OTP service unavailable. Contact admin.'}), 503

        twilio_client.verify.v2.services(SERVICE_SID) \
            .verifications \
            .create(to=doctor.email, channel='email')

        return jsonify({
            'success':    True,
            'message':    'OTP sent via email',
            'identifier': doctor.email,
            'channel':    'email',
        }), 200

    except Exception as e:
        print(f"ERROR in login: {e}")
        return jsonify({'error': str(e)}), 500


# ── VERIFY OTP ─────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)

        identifier = (data.get('identifier') or '').strip()
        code       = (data.get('code') or '').strip()

        if not identifier or not code:
            return jsonify({'error': 'Identifier and code are required'}), 400

        if not twilio_client:
            return jsonify({'error': 'OTP service unavailable'}), 503

        result = twilio_client.verify.v2.services(SERVICE_SID) \
            .verification_checks \
            .create(to=identifier, code=code)

        if result.status != 'approved':
            return jsonify({'error': 'Invalid or expired code'}), 401

        doctor = (
            Doctor.query.filter_by(email=identifier).first()
            if '@' in identifier
            else Doctor.query.filter_by(phone=identifier).first()
        )
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        access_token = create_access_token(
            identity=str(doctor.id),
            expires_delta=timedelta(days=7)
        )
        return jsonify({
            'success':      True,
            'access_token': access_token,
            'doctor': {
                'id':        doctor.id,
                'name':      doctor.name,
                'email':     doctor.email,
                'phone':     doctor.phone,
                'specialty': doctor.specialty,
            }
        }), 200

    except Exception as e:
        print(f"ERROR in verify_otp: {e}")
        return jsonify({'error': str(e)}), 500
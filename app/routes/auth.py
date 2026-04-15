from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from datetime import timedelta
import os
import re

auth_bp = Blueprint('auth', __name__)

# ── Twilio config ─────────────────────────────────────────────────────────
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
SERVICE_SID = os.getenv("TWILIO_SERVICE_SID")
DEV_MODE    = os.getenv("DEV_MODE", "false").lower() == "true"

# ✅ FIX: lazy init — don't crash at startup if Twilio creds are missing
def get_twilio_client():
    if not ACCOUNT_SID or not AUTH_TOKEN:
        raise ValueError("Twilio credentials missing in .env")
    from twilio.rest import Client
    return Client(ACCOUNT_SID, AUTH_TOKEN)


# ── Validators ────────────────────────────────────────────────────────────
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone(phone):
    pattern = r'^(\+966|05)\d{8}$'
    return re.match(pattern, phone) is not None


def normalize_phone(phone: str) -> str:
    """Convert 05XXXXXXXX → +966XXXXXXXXX"""
    if phone.startswith('05'):
        return '+966' + phone[1:]
    return phone


# ── SIGNUP ────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validate required fields
        if not data.get('name') or not str(data['name']).strip():
            return jsonify({'error': 'Name is required'}), 400
        if not data.get('password') or len(data['password']) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        email = data.get('email', '').strip().lower()
        phone = data.get('phone', '').strip()

        if not email:
            return jsonify({'error': 'Email is required'}), 400
        if not phone:
            return jsonify({'error': 'Phone is required'}), 400
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        if not validate_phone(phone):
            return jsonify({'error': 'Invalid phone. Use +966XXXXXXXXX or 05XXXXXXXX'}), 400
        if Doctor.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 400

        phone_normalized = normalize_phone(phone)
        if Doctor.query.filter_by(phone=phone_normalized).first():
            return jsonify({'error': 'Phone already registered'}), 400

        doctor = Doctor(
            name=data['name'].strip(),
            email=email,
            phone=phone_normalized,
            specialty=data.get('specialty', 'Thyroid Specialist'),
            license_number=data.get('license_number', ''),
            status='pending'  # ✅ requires admin approval
        )
        doctor.set_password(data['password'])
        db.session.add(doctor)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Registration successful. Awaiting admin approval.',
            'doctor': doctor.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"❌ ERROR in signup: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ── LOGIN ─────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        identifier = data.get('identifier', '').strip().lower()
        password   = data.get('password', '').strip()

        if not identifier:
            return jsonify({'error': 'Email is required'}), 400
        if not password:
            return jsonify({'error': 'Password is required'}), 400

        doctor = Doctor.query.filter_by(email=identifier).first()
        if not doctor or not doctor.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401

        # ✅ FIX: Block inactive/pending/rejected doctors
        if doctor.status == 'pending':
            return jsonify({'error': 'Your account is pending admin approval'}), 403
        if doctor.status == 'rejected':
            return jsonify({'error': 'Your account has been rejected. Please contact support'}), 403
        if doctor.status == 'inactive':
            return jsonify({'error': 'Your account has been deactivated. Please contact support'}), 403

        # ── DEV MODE: skip OTP ──
        if DEV_MODE:
            print("⚠️  DEV_MODE ON — skipping OTP")
            access_token = create_access_token(
                identity=str(doctor.id),
                expires_delta=timedelta(days=7)
            )
            return jsonify({
                'success':      True,
                'access_token': access_token,
                'doctor':       doctor.to_dict()
            }), 200

        # ── PRODUCTION: send OTP via Twilio ──
        try:
            client = get_twilio_client()
            client.verify.v2.services(SERVICE_SID) \
                .verifications \
                .create(to=doctor.email, channel="email")
        except Exception as twilio_err:
            print(f"❌ Twilio error: {twilio_err}")
            return jsonify({'error': 'Failed to send OTP. Please try again.'}), 500

        return jsonify({
            'success':    True,
            'message':    'OTP sent to your email',
            'identifier': doctor.email,
            'channel':    'email'
        }), 200

    except Exception as e:
        print(f"❌ ERROR in login: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ── VERIFY OTP ────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        identifier = data.get('identifier', '').strip()
        code       = data.get('code', '').strip()

        if not identifier or not code:
            return jsonify({'error': 'Identifier and OTP code are required'}), 400

        # ✅ FIX: validate OTP via Twilio
        try:
            client = get_twilio_client()
            result = client.verify.v2.services(SERVICE_SID) \
                .verification_checks \
                .create(to=identifier, code=code)
        except Exception as twilio_err:
            print(f"❌ Twilio verify error: {twilio_err}")
            return jsonify({'error': 'OTP verification failed. Please try again.'}), 500

        if result.status != 'approved':
            return jsonify({'error': 'Invalid or expired OTP code'}), 401

        # Find doctor by email or phone
        if '@' in identifier:
            doctor = Doctor.query.filter_by(email=identifier).first()
        else:
            doctor = Doctor.query.filter_by(phone=identifier).first()

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        access_token = create_access_token(
            identity=str(doctor.id),
            expires_delta=timedelta(days=7)
        )
        return jsonify({
            'success':      True,
            'access_token': access_token,
            'doctor':       doctor.to_dict()
        }), 200

    except Exception as e:
        print(f"❌ ERROR in verify_otp: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ── SEND PHONE OTP ────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/send-phone-otp', methods=['POST', 'OPTIONS'])
def send_phone_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data  = request.get_json(force=True, silent=True)
        email = data.get('email', '').strip().lower()

        doctor = Doctor.query.filter_by(email=email).first()
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404
        if not doctor.phone:
            return jsonify({'error': 'No phone number on file'}), 400

        phone = normalize_phone(doctor.phone)

        try:
            client = get_twilio_client()
            client.verify.v2.services(SERVICE_SID) \
                .verifications \
                .create(to=phone, channel="sms")
        except Exception as twilio_err:
            print(f"❌ Twilio SMS error: {twilio_err}")
            return jsonify({'error': 'Failed to send SMS OTP'}), 500

        return jsonify({
            'success':    True,
            'message':    'OTP sent via SMS',
            'identifier': phone,
            'channel':    'sms'
        }), 200

    except Exception as e:
        print(f"❌ ERROR in send_phone_otp: {str(e)}")
        return jsonify({'error': str(e)}), 500

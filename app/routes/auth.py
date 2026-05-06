from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from app import limiter
from datetime import timedelta
import logging
import os
import re

auth_bp = Blueprint('auth', __name__)
logger  = logging.getLogger('diagnovate.auth')

DEV_MODE    = os.getenv("DEV_MODE", "false").lower() == "true"
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
SERVICE_SID = os.getenv("TWILIO_SERVICE_SID")

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


def _email_html_wrapper(body_html: str) -> str:
    """Wrap body HTML in a branded Diagnovate email template."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Helvetica Neue',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 16px">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
        <tr><td style="background:linear-gradient(135deg,#0D9488,#0891B2);padding:28px 40px">
          <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px">Diagnovate</h1>
          <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:13px">Clinical AI Platform</p>
        </td></tr>
        <tr><td style="padding:40px">{body_html}</td></tr>
        <tr><td style="padding:20px 40px;border-top:1px solid #e2e8f0;background:#f8fafc">
          <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
            &copy; 2025 Diagnovate &middot; This is an automated message, please do not reply.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ── SIGNUP ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per hour")
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
        logger.exception('signup error')
        return jsonify({'error': 'An internal error occurred'}), 500


# ── LOGIN ──────────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per minute; 20 per hour")
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
        logger.exception('login error')
        return jsonify({'error': 'An internal error occurred'}), 500


# ── VERIFY OTP ─────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/verify-otp', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per minute")
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
        logger.exception('verify_otp error')
        return jsonify({'error': 'An internal error occurred'}), 500


# ── SEND PHONE OTP ─────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/send-phone-otp', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per minute")
def send_phone_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data       = request.get_json(force=True, silent=True) or {}
        identifier = (data.get('identifier') or '').strip()
        if not identifier:
            return jsonify({'error': 'identifier and method ("sms" or "email") are required'}), 400

        if DEV_MODE:
            print(f"⚠️  DEV_MODE — skipping SMS OTP for {identifier}")
            return jsonify({'success': True, 'message': 'OTP sent (DEV_MODE)'}), 200

        if not twilio_client:
            return jsonify({'error': 'OTP service unavailable'}), 503

        twilio_client.verify.v2.services(SERVICE_SID) \
            .verifications.create(to=identifier, channel='sms')

        return jsonify({'success': True, 'message': 'SMS OTP sent'}), 200

    except Exception as e:
        logger.exception('send_phone_otp error')
        return jsonify({'error': 'An internal error occurred'}), 500


# ── SEND EMAIL OTP ─────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/send-email-otp', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per minute")
def send_email_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data       = request.get_json(force=True, silent=True) or {}
        identifier = (data.get('identifier') or '').strip()
        if not identifier:
            return jsonify({'error': 'identifier and method ("sms" or "email") are required'}), 400

        if DEV_MODE:
            print(f"⚠️  DEV_MODE — skipping email OTP for {identifier}")
            return jsonify({'success': True, 'message': 'OTP sent (DEV_MODE)'}), 200

        if not twilio_client:
            return jsonify({'error': 'OTP service unavailable'}), 503

        twilio_client.verify.v2.services(SERVICE_SID) \
            .verifications.create(to=identifier, channel='email')

        return jsonify({'success': True, 'message': 'Email OTP sent'}), 200

    except Exception as e:
        logger.exception('send_email_otp error')
        return jsonify({'error': 'An internal error occurred'}), 500


# ── AUTH STATUS ────────────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/status', methods=['GET', 'OPTIONS'])
def auth_status():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request()
        doctor_id = get_jwt_identity()
        doctor    = Doctor.query.get(int(doctor_id))
        if not doctor:
            return jsonify({'authenticated': False, 'error': 'Doctor not found'}), 404
        return jsonify({
            'authenticated': True,
            'status':        doctor.status,
            'doctor_id':     doctor.id,
        }), 200
    except Exception:
        return jsonify({'authenticated': False}), 401

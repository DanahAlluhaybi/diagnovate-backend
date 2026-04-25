from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from datetime import datetime, timedelta
from twilio.rest import Client
import os, re, resend, random
from werkzeug.security import generate_password_hash

LOCKOUT_MAX_ATTEMPTS = 5
LOCKOUT_DURATION     = timedelta(minutes=30)

_email_otps = {}  # {email: {code, expires}}

auth_bp = Blueprint('auth', __name__)

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN")
SERVICE_SID  = os.getenv("TWILIO_SERVICE_SID")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://diagnovate.org")

def is_dev_mode():
    return os.getenv("DEV_MODE", "false").lower() == "true"

resend.api_key = os.getenv("RESEND_API_KEY", "")

def get_twilio():
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        raise RuntimeError("Twilio credentials not configured")
    return Client(account_sid, auth_token)


def validate_email(email):
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None

def validate_phone(phone):
    return re.match(r'^\+966\d{9}$', phone) is not None

def normalize_phone(phone):
    if phone.startswith('05') and len(phone) == 10:
        return '+966' + phone[1:]
    return phone

def _email_html_wrapper(content: str) -> str:
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#ffffff">
  <div style="background:#0D9488;padding:24px 32px;border-radius:8px 8px 0 0">
    <h1 style="color:white;margin:0;font-size:24px;letter-spacing:1px">Diagnovate</h1>
  </div>
  <div style="padding:40px 32px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px">
    {content}
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:32px 0">
    <p style="color:#9ca3af;font-size:12px;margin:0">Diagnovate &mdash; AI-powered thyroid diagnosis platform.<br>If you did not request this email, you can safely ignore it.</p>
  </div>
</div>"""


def send_email_otp(email: str, doctor_name: str, code: str):
    try:
        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": email,
            "subject": "Diagnovate – Your Email Verification Code",
            "html": _email_html_wrapper(f"""
    <h2 style="color:#111827;margin:0 0 8px">Verify your email</h2>
    <p style="color:#6b7280;margin:0 0 32px">Hi Dr. {doctor_name}, enter the code below to verify your email address.</p>
    <div style="text-align:center;margin:0 0 32px">
      <div style="display:inline-block;background:#f0fdf4;border:2px solid #0D9488;border-radius:12px;padding:24px 40px">
        <span style="font-size:48px;font-weight:700;letter-spacing:12px;color:#0D9488;font-family:'Courier New',monospace">{code}</span>
      </div>
    </div>
    <p style="color:#6b7280;text-align:center;margin:0">This code expires in <strong>15 minutes</strong>.</p>""")
        })
        print(f"📧 Email OTP sent to {email}")
    except Exception as e:
        print(f"⚠️ Failed to send email OTP: {e}")


def send_welcome_email(email, doctor_name):
    try:
        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": email,
            "subject": "Welcome to Diagnovate!",
            "html": _email_html_wrapper(f"""
    <h2 style="color:#111827;margin:0 0 8px">Welcome, Dr. {doctor_name}!</h2>
    <p style="color:#6b7280;margin:0 0 16px">Your registration request has been received successfully.</p>
    <p style="color:#6b7280;margin:0 0 32px">Our admin team will review your details and notify you by email once a decision has been made.</p>
    <div style="text-align:center;margin:0 0 32px">
      <a href="{FRONTEND_URL}/pending-approval" style="background:#0D9488;color:white;padding:14px 32px;text-decoration:none;border-radius:6px;font-weight:600;font-size:15px">
        Track Your Request
      </a>
    </div>""")
        })
        print(f"📧 Welcome email sent to {email}")
    except Exception as e:
        print(f"⚠️ Failed to send welcome email: {e}")


@auth_bp.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data      = request.get_json(force=True, silent=True)
        name      = (data.get('name') or '').strip()
        email     = (data.get('email') or '').strip()
        phone     = normalize_phone((data.get('phone') or '').strip())
        password  = (data.get('password') or '')
        specialty = (data.get('specialty') or 'Thyroid Specialist').strip()

        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not email or not validate_email(email):
            return jsonify({'error': 'Invalid email address'}), 400
        if not phone or not validate_phone(phone):
            return jsonify({'error': 'Invalid phone number, use +966XXXXXXXXX or 05XXXXXXXX'}), 400
        if not password or len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        INCOMPLETE_STATUSES = ['rejected', 'pending_otp', 'pending_email_otp']

        stale = Doctor.query.filter(
            db.or_(Doctor.email==email, Doctor.phone==phone),
            Doctor.status.in_(INCOMPLETE_STATUSES)
        ).all()
        for d in stale:
            db.session.delete(d)
        db.session.commit()

        existing_email = Doctor.query.filter_by(email=email).filter(
            Doctor.status.notin_(INCOMPLETE_STATUSES)
        ).first()
        if existing_email:
            return jsonify({'error': 'Email is already registered'}), 400

        existing_phone = Doctor.query.filter_by(phone=phone).filter(
            Doctor.status.notin_(INCOMPLETE_STATUSES)
        ).first()
        if existing_phone:
            return jsonify({'error': 'Phone number is already registered'}), 400
        doctor = Doctor(name=name, email=email, phone=phone, specialty=specialty, status='pending_otp')
        doctor.password_hash = generate_password_hash(password)
        db.session.add(doctor)
        db.session.commit()

        if is_dev_mode():
            print(f"⚠️ DEV_MODE — OTP للرقم {phone} هو 123456")
            return jsonify({
                'success':    True,
                'message':    'DEV: كود OTP هو 123456',
                'identifier': phone,
            }), 200

        get_twilio().verify.v2.services(SERVICE_SID) \
            .verifications.create(to=phone, channel='sms')

        return jsonify({
            'success':    True,
            'message':    f'تم إرسال OTP إلى {phone}',
            'identifier': phone,
        }), 200

    except Exception as e:
        print(f"[SIGNUP ERROR] {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/verify-signup', methods=['POST', 'OPTIONS'])
def verify_signup():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data  = request.get_json(force=True, silent=True)
        phone = normalize_phone((data.get('identifier') or '').strip())
        code  = (data.get('code') or '').strip()

        if not phone or not code:
            return jsonify({'error': 'رقم الهاتف والكود مطلوبان'}), 400

        doctor = Doctor.query.filter_by(phone=phone, status='pending_otp').first()
        if not doctor:
            return jsonify({'error': 'لا يوجد تسجيل معلق لهذا الرقم، سجّل من جديد'}), 400

        if is_dev_mode():
            if code != '123456':
                return jsonify({'error': 'كود خاطئ (DEV: استخدم 123456)'}), 401
        else:
            result = get_twilio().verify.v2.services(SERVICE_SID) \
                .verification_checks.create(to=phone, code=code)
            if result.status != 'approved':
                return jsonify({'error': 'الكود غير صحيح أو منتهي الصلاحية'}), 401

        email_code = '654321' if is_dev_mode() else str(random.randint(100000, 999999))
        _email_otps[doctor.email] = {
            'code':    email_code,
            'expires': datetime.utcnow() + timedelta(minutes=15),
        }
        doctor.status = 'pending_email_otp'
        db.session.commit()

        if is_dev_mode():
            print(f"⚠️ DEV_MODE — Email OTP for {doctor.email} is 654321")
        else:
            send_email_otp(doctor.email, doctor.name, email_code)

        return jsonify({
            'success':    True,
            'next_step':  'verify_email',
            'email':      doctor.email,
            'message':    f'SMS verified. A 6-digit code has been sent to {doctor.email}',
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"[VERIFY SIGNUP ERROR] {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp():
    return verify_signup()


@auth_bp.route('/api/auth/verify-email-otp', methods=['POST', 'OPTIONS'])
def verify_email_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data  = request.get_json(force=True, silent=True)
        email = (data.get('email') or '').strip().lower()
        code  = (data.get('code') or '').strip()

        if not email or not code:
            return jsonify({'error': 'Email and code are required'}), 400

        doctor = Doctor.query.filter_by(email=email, status='pending_email_otp').first()
        if not doctor:
            return jsonify({'error': 'No pending email verification for this address'}), 400

        entry = _email_otps.get(email)
        if not entry:
            return jsonify({'error': 'No OTP found — please restart signup'}), 400
        if datetime.utcnow() > entry['expires']:
            _email_otps.pop(email, None)
            return jsonify({'error': 'Code has expired — please restart signup'}), 400
        if code != entry['code']:
            return jsonify({'error': 'Incorrect code'}), 401

        _email_otps.pop(email, None)
        doctor.status = 'pending'
        db.session.commit()

        send_welcome_email(doctor.email, doctor.name)

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
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"[VERIFY EMAIL OTP ERROR] {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data       = request.get_json(force=True, silent=True)
        identifier = (data.get('identifier') or '').strip()
        password   = (data.get('password') or '').strip()

        if not identifier or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        doctor = Doctor.query.filter_by(email=identifier).first()

        if doctor and doctor.locked_until and doctor.locked_until > datetime.utcnow():
            remaining = int((doctor.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
            return jsonify({
                'error': f'Account locked due to too many failed attempts. Try again in {remaining} minute(s).'
            }), 429

        if not doctor or not doctor.check_password(password):
            if doctor:
                doctor.failed_attempts = (doctor.failed_attempts or 0) + 1
                if doctor.failed_attempts >= LOCKOUT_MAX_ATTEMPTS:
                    doctor.locked_until = datetime.utcnow() + LOCKOUT_DURATION
                    db.session.commit()
                    return jsonify({
                        'error': f'Account locked after {LOCKOUT_MAX_ATTEMPTS} failed attempts. Try again in 30 minutes.'
                    }), 429
                db.session.commit()
                remaining_attempts = LOCKOUT_MAX_ATTEMPTS - doctor.failed_attempts
                return jsonify({
                    'error': f'Invalid email or password. {remaining_attempts} attempt(s) remaining before lockout.'
                }), 401
            return jsonify({'error': 'Invalid email or password'}), 401

        if doctor.status == 'pending_otp':
            return jsonify({'error': 'Please complete phone verification first'}), 403
        if doctor.status == 'pending_email_otp':
            return jsonify({'error': 'Please complete email verification first'}), 403
        if doctor.status == 'pending':
            return jsonify({'error': 'Your account is under review. You will be notified once approved by admin'}), 403
        if doctor.status == 'rejected':
            return jsonify({'error': 'Your registration was rejected. Please contact support'}), 403

        doctor.failed_attempts = 0
        doctor.locked_until    = None
        doctor.last_login      = datetime.utcnow()
        doctor.last_ip         = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        db.session.commit()

        access_token = create_access_token(identity=str(doctor.id))
        return jsonify({
            'success': True,
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
        print(f"[LOGIN ERROR] {e}")
        return jsonify({'error': str(e)}), 500
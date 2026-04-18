from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from datetime import timedelta
from twilio.rest import Client
import os, re, resend
from werkzeug.security import generate_password_hash

auth_bp = Blueprint('auth', __name__)

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN")
SERVICE_SID  = os.getenv("TWILIO_SERVICE_SID")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://diagnovate.org")

def is_dev_mode():
    return os.getenv("DEV_MODE", "false").lower() == "true"

resend.api_key = os.getenv("RESEND_API_KEY", "")

_twilio = None
def get_twilio():
    global _twilio
    if _twilio is None:
        if not ACCOUNT_SID or not AUTH_TOKEN:
            raise RuntimeError("Twilio credentials not configured")
        _twilio = Client(ACCOUNT_SID, AUTH_TOKEN)
    return _twilio

_pending = {}

def validate_email(email):
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None

def validate_phone(phone):
    return re.match(r'^\+966\d{9}$', phone) is not None

def normalize_phone(phone):
    if phone.startswith('05') and len(phone) == 10:
        return '+966' + phone[1:]
    return phone

def send_welcome_email(email, doctor_name):
    try:
        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": email,
            "subject": "Welcome to Diagnovate!",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #0066CC; padding: 24px; border-radius: 8px 8px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 24px;">Diagnovate</h1>
                </div>
                <div style="padding: 32px; border: 1px solid #e0e0e0; border-radius: 0 0 8px 8px;">
                    <h2 style="color: #333;">Welcome, Dr. {doctor_name}! 👋</h2>
                    <p style="color: #555;">Your account has been successfully created.</p>
                    <p style="color: #555;">You can now log in and start using Diagnovate to manage your patients and diagnoses.</p>
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{FRONTEND_URL}/login" style="
                            background-color: #0066CC;
                            color: white;
                            padding: 14px 32px;
                            text-decoration: none;
                            border-radius: 6px;
                            display: inline-block;
                            font-weight: bold;
                            font-size: 16px;
                        ">Go to Diagnovate</a>
                    </div>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
                    <p style="color: #aaa; font-size: 12px;">Best regards,<br>Diagnovate Team</p>
                </div>
            </div>
            """
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
            return jsonify({'error': 'الاسم مطلوب'}), 400
        if not email or not validate_email(email):
            return jsonify({'error': 'البريد الإلكتروني غير صحيح'}), 400
        if not phone or not validate_phone(phone):
            return jsonify({'error': 'رقم الهاتف غير صحيح، استخدم +966XXXXXXXXX أو 05XXXXXXXX'}), 400
        if not password or len(password) < 6:
            return jsonify({'error': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400

        if Doctor.query.filter_by(email=email).first():
            return jsonify({'error': 'البريد الإلكتروني مسجل مسبقاً'}), 400
        if Doctor.query.filter_by(phone=phone).first():
            return jsonify({'error': 'رقم الهاتف مسجل مسبقاً'}), 400

        _pending[phone] = {
            'name':      name,
            'email':     email,
            'phone':     phone,
            'password':  generate_password_hash(password),
            'specialty': specialty,
        }

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

        pending = _pending.get(phone)
        if not pending:
            return jsonify({'error': 'لا يوجد تسجيل معلق لهذا الرقم، سجّل من جديد'}), 400

        if is_dev_mode():
            if code != '123456':
                return jsonify({'error': 'كود خاطئ (DEV: استخدم 123456)'}), 401
        else:
            result = get_twilio().verify.v2.services(SERVICE_SID) \
                .verification_checks.create(to=phone, code=code)
            if result.status != 'approved':
                return jsonify({'error': 'الكود غير صحيح أو منتهي الصلاحية'}), 401

        if Doctor.query.filter_by(email=pending['email']).first():
            _pending.pop(phone, None)
            return jsonify({'error': 'البريد الإلكتروني مسجل مسبقاً'}), 400
        if Doctor.query.filter_by(phone=phone).first():
            _pending.pop(phone, None)
            return jsonify({'error': 'رقم الهاتف مسجل مسبقاً'}), 400

        doctor = Doctor(
            name=pending['name'],
            email=pending['email'],
            phone=pending['phone'],
            specialty=pending['specialty'],
        )
        doctor.password_hash = pending['password']
        db.session.add(doctor)
        db.session.commit()

        _pending.pop(phone, None)

        send_welcome_email(pending['email'], pending['name'])

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
        print(f"[VERIFY SIGNUP ERROR] {e}")
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
            return jsonify({'error': 'البريد وكلمة المرور مطلوبان'}), 400

        doctor = Doctor.query.filter_by(email=identifier).first()
        if not doctor or not doctor.check_password(password):
            return jsonify({'error': 'البريد أو كلمة المرور غير صحيحة'}), 401

        access_token = create_access_token(
            identity=str(doctor.id),
            expires_delta=timedelta(days=7)
        )
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
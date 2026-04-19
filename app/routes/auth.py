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

def send_welcome_email(email, doctor_name):
    try:
        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": email,
            "subject": "Welcome to Diagnovate!",
            "html": f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
    <div style="background:#0066CC;padding:24px;border-radius:8px 8px 0 0">
        <h1 style="color:white;margin:0">Diagnovate</h1>
    </div>
    <div style="padding:32px;border:1px solid #e0e0e0;border-radius:0 0 8px 8px">
        <h2>Thank you for joining Diagnovate, Dr. {doctor_name}! 👋</h2>
        <p>Your registration request has been received successfully.</p>
        <p>Our admin team will review your request and you will receive an email with the approval or rejection decision.</p>
        <p>You can track your request status by visiting your profile page.</p>
        <div style="text-align:center;margin:32px 0">
            <a href="{FRONTEND_URL}/pending-approval" style="background:#0066CC;color:white;padding:14px 32px;text-decoration:none;border-radius:6px;font-weight:bold">
                Track Your Request
            </a>
        </div>
        <p style="color:#aaa;font-size:12px">Best regards,<br>Diagnovate Team</p>
    </div>
</div>"""
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

        Doctor.query.filter_by(phone=phone, status='pending_otp').delete()
        Doctor.query.filter_by(email=email, status='pending_otp').delete()
        db.session.commit()
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
        print(f"[VERIFY SIGNUP ERROR] {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp():
    return verify_signup()


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

        if doctor.status == 'pending_otp':
            return jsonify({'error': 'Please complete phone verification first'}), 403
        if doctor.status == 'pending':
            return jsonify({'error': 'Your account is under review. You will be notified once approved by admin'}), 403
        if doctor.status == 'rejected':
            return jsonify({'error': 'Your registration was rejected. Please contact support'}), 403

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
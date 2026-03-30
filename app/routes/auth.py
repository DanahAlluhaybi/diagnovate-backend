from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from datetime import timedelta
from twilio.rest import Client
import os
import re

auth_bp = Blueprint('auth', __name__)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
SERVICE_SID = os.getenv("TWILIO_SERVICE_SID")
DEV_MODE    = os.getenv("DEV_MODE", "false").lower() == "true"

twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone(phone):
    pattern = r'^(\+966|05)\d{8}$'
    return re.match(pattern, phone) is not None


@auth_bp.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        print("=" * 50)
        print("SIGNUP REQUEST RECEIVED")
        print(f"Data received: {data}")

        if not data:
            return jsonify({'error': 'No data provided'}), 400
        if not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400
        if not data.get('password') or len(data['password']) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()

        if not email:
            return jsonify({'error': 'Email is required'}), 400
        if not phone:
            return jsonify({'error': 'Phone is required'}), 400
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        if not validate_phone(phone):
            return jsonify({'error': 'Invalid phone format. Use +966XXXXXXXXX'}), 400
        if Doctor.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 400
        if Doctor.query.filter_by(phone=phone).first():
            return jsonify({'error': 'Phone already registered'}), 400

        doctor = Doctor(
            name=data['name'],
            email=email,
            phone=phone,
            specialty=data.get('specialty', 'Thyroid Specialist')
        )
        doctor.set_password(data['password'])
        db.session.add(doctor)
        db.session.commit()

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
                'specialty': doctor.specialty
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"ERROR in signup: {str(e)}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        print("=" * 50)
        print("LOGIN REQUEST RECEIVED")
        print(f"Raw data: {data}")
        print(f"DEV_MODE: {DEV_MODE}")

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        identifier = data.get('identifier', '').strip()
        password   = data.get('password', '').strip()

        print(f"Identifier: {identifier}, Password length: {len(password)}")

        if not identifier:
            return jsonify({'error': 'Email is required'}), 400
        if not password:
            return jsonify({'error': 'Password is required'}), 400

        doctor = Doctor.query.filter_by(email=identifier).first()
        if not doctor or not doctor.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401

        # ── DEV MODE: تخطى OTP وارجع Token مباشرة ──
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
                    'specialty': doctor.specialty
                }
            }), 200

        # ── PRODUCTION: أرسل OTP ──
        twilio_client.verify.v2.services(SERVICE_SID) \
            .verifications \
            .create(to=doctor.email, channel="email")

        return jsonify({
            'success':    True,
            'message':    'OTP sent via email',
            'identifier': doctor.email,
            'channel':    'email'
        }), 200

    except Exception as e:
        print(f"ERROR in login: {str(e)}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True)
        print(f"VERIFY OTP data: {data}")

        identifier = data.get('identifier', '').strip()
        code       = data.get('code', '').strip()

        if not identifier or not code:
            return jsonify({'error': 'Identifier and code are required'}), 400

        result = twilio_client.verify.v2.services(SERVICE_SID) \
            .verification_checks \
            .create(to=identifier, code=code)

        if result.status != 'approved':
            return jsonify({'error': 'Invalid or expired code'}), 401

        doctor = Doctor.query.filter_by(email=identifier).first() \
            if '@' in identifier else Doctor.query.filter_by(phone=identifier).first()

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
                'specialty': doctor.specialty
            }
        }), 200

    except Exception as e:
        print(f"ERROR in verify_otp: {str(e)}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/send-phone-otp', methods=['POST', 'OPTIONS'])
def send_phone_otp():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data  = request.get_json(force=True, silent=True)
        email = data.get('email', '').strip()

        doctor = Doctor.query.filter_by(email=email).first()
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404
        if not doctor.phone:
            return jsonify({'error': 'No phone number on file'}), 400

        phone = doctor.phone
        if phone.startswith('05'):
            phone = '+966' + phone[1:]

        twilio_client.verify.v2.services(SERVICE_SID) \
            .verifications \
            .create(to=phone, channel="sms")

        return jsonify({
            'success':    True,
            'message':    'OTP sent via sms',
            'identifier': phone,
            'channel':    'sms'
        }), 200

    except Exception as e:
        print(f"ERROR in send_phone_otp: {str(e)}")
        return jsonify({'error': str(e)}), 500
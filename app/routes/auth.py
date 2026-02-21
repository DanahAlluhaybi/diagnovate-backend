from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from datetime import timedelta
import re

auth_bp = Blueprint('auth', __name__)


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


@auth_bp.route('/api/auth/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        print("=" * 50)
        print("SIGNUP REQUEST RECEIVED")
        print(f"Data received: {data}")

        if not data:
            print("❌ No data received")
            return jsonify({'error': 'No data provided'}), 400

        # Validation
        if not data.get('name'):
            print("❌ Name missing")
            return jsonify({'error': 'Name is required'}), 400

        if not data.get('email'):
            print("❌ Email missing")
            return jsonify({'error': 'Email is required'}), 400

        if not data.get('password'):
            print("❌ Password missing")
            return jsonify({'error': 'Password is required'}), 400

        if not validate_email(data['email']):
            print(f"❌ Invalid email format: {data['email']}")
            return jsonify({'error': 'Invalid email format'}), 400

        if len(data['password']) < 6:
            print("❌ Password too short")
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        # Check if doctor exists
        existing = Doctor.query.filter_by(email=data['email']).first()
        if existing:
            print(f"❌ Email already exists: {data['email']}")
            return jsonify({'error': 'Email already registered'}), 400

        # Create new doctor
        print(f"✅ Creating new doctor: {data['email']}")
        doctor = Doctor(
            name=data['name'],
            email=data['email'],
            specialty=data.get('specialty', 'Thyroid Specialist')
        )
        doctor.set_password(data['password'])
        print(f"Password hash created: {doctor.password_hash[:50]}...")

        db.session.add(doctor)
        db.session.commit()

        print(f"✅ Doctor saved with ID: {doctor.id}")

        access_token = create_access_token(
            identity=doctor.id,
            expires_delta=timedelta(days=7)
        )

        return jsonify({
            'success': True,
            'access_token': access_token,
            'doctor': {
                'id': doctor.id,
                'name': doctor.name,
                'email': doctor.email,
                'specialty': doctor.specialty
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"❌ ERROR in signup: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        print("=" * 50)
        print("LOGIN REQUEST RECEIVED")
        print(f"Email: {data.get('email') if data else 'No data'}")

        if not data:
            print("❌ No data received")
            return jsonify({'error': 'No data provided'}), 400

        if not data.get('email') or not data.get('password'):
            print("❌ Missing email or password")
            return jsonify({'error': 'Email and password required'}), 400

        # البحث عن الدكتور
        print(f"🔍 Searching for doctor with email: {data['email']}")
        doctor = Doctor.query.filter_by(email=data['email']).first()

        if not doctor:
            print(f"❌ No doctor found with email: {data['email']}")
            # نشوف كل الدكاترة للتحقق
            all_doctors = Doctor.query.all()
            print(f"Total doctors in DB: {len(all_doctors)}")
            for d in all_doctors:
                print(f"  - {d.email}")
            return jsonify({'error': 'Invalid email or password'}), 401

        print(f"✅ Doctor found: {doctor.email}")
        print(f"Stored hash: {doctor.password_hash[:50]}...")

        # التحقق من كلمة المرور
        password_check = doctor.check_password(data['password'])
        print(f"Password check result: {password_check}")

        if password_check:
            print("✅ Password correct")
            access_token = create_access_token(
                identity=doctor.id,
                expires_delta=timedelta(days=7)
            )

            return jsonify({
                'success': True,
                'access_token': access_token,
                'doctor': {
                    'id': doctor.id,
                    'name': doctor.name,
                    'email': doctor.email,
                    'specialty': doctor.specialty
                }
            }), 200

        print("❌ Password incorrect")
        return jsonify({'error': 'Invalid email or password'}), 401

    except Exception as e:
        print(f"❌ ERROR in login: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
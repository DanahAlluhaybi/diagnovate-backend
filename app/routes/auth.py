from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.models import db, Doctor
from datetime import timedelta
import re

auth_bp = Blueprint('auth', __name__)


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


@auth_bp.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        if not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400
        if not data.get('email'):
            return jsonify({'error': 'Email is required'}), 400
        if not data.get('password'):
            return jsonify({'error': 'Password is required'}), 400
        if not validate_email(data['email']):
            return jsonify({'error': 'Invalid email format'}), 400
        if len(data['password']) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        existing = Doctor.query.filter_by(email=data['email']).first()
        if existing:
            return jsonify({'error': 'Email already registered'}), 400

        doctor = Doctor(
            name=data['name'],
            email=data['email'],
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
            'token': access_token,          # ← فرونت يدور 'token'
            'access_token': access_token,   # ← احتياطي
            'user': {
                'id':        doctor.id,
                'name':      doctor.name,
                'email':     doctor.email,
                'specialty': doctor.specialty
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        if not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password required'}), 400

        doctor = Doctor.query.filter_by(email=data['email']).first()
        if not doctor or not doctor.check_password(data['password']):
            return jsonify({'error': 'Invalid email or password'}), 401

        access_token = create_access_token(
            identity=str(doctor.id),
            expires_delta=timedelta(days=7)
        )

        return jsonify({
            'success': True,
            'token': access_token,          # ← فرونت يدور 'token'
            'access_token': access_token,   # ← احتياطي
            'user': {
                'id':        doctor.id,
                'name':      doctor.name,
                'email':     doctor.email,
                'specialty': doctor.specialty
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
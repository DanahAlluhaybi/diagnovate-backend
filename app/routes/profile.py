from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Doctor, Case, Patient

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/api/test', methods=['GET'])
def test():
    return jsonify({'message': 'Profile route is working!'}), 200


# ── GET Profile ────────────────────────────────────────────────────────────────
@profile_bp.route('/api/profile', methods=['GET'])
@jwt_required()
def get_profile():
    try:
        # FIX: get_jwt_identity() returns str — cast to int
        doctor_id = int(get_jwt_identity())
        doctor    = Doctor.query.get(doctor_id)

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        total_cases    = Case.query.filter_by(doctor_id=doctor_id).count()
        active_cases   = Case.query.filter_by(doctor_id=doctor_id, status='active').count()
        total_patients = Patient.query.filter_by(doctor_id=doctor_id).count()

        return jsonify({
            'success': True,
            'doctor': doctor.to_dict(),
            'stats': {
                'total_cases':    total_cases,
                'active_cases':   active_cases,
                'total_patients': total_patients,
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── UPDATE Profile ─────────────────────────────────────────────────────────────
@profile_bp.route('/api/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    try:
        # FIX: cast to int
        doctor_id = int(get_jwt_identity())
        doctor    = Doctor.query.get(doctor_id)

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        if data.get('name'):
            doctor.name = data['name'].strip()
        if data.get('specialty'):
            doctor.specialty = data['specialty'].strip()
        if data.get('phone'):
            doctor.phone = data['phone'].strip()
        if data.get('license_number'):
            doctor.license_number = data['license_number'].strip()

        # Password change (optional)
        if data.get('new_password'):
            if not data.get('current_password'):
                return jsonify({'error': 'Current password is required to change password'}), 400
            if not doctor.check_password(data['current_password']):
                return jsonify({'error': 'Current password is incorrect'}), 401
            if len(data['new_password']) < 6:
                return jsonify({'error': 'New password must be at least 6 characters'}), 400
            doctor.set_password(data['new_password'])

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'doctor':  doctor.to_dict(),
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
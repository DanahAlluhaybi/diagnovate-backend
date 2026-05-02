from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Doctor, Case, Patient

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/api/test', methods=['GET'])
def test():
    return jsonify({'message': 'Diagnovate backend is running!'}), 200


@profile_bp.route('/api/profile', methods=['GET'])
@jwt_required()
def get_profile():
    try:
        doctor_id = int(get_jwt_identity())
        doctor    = Doctor.query.get(doctor_id)

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        total_cases    = Case.query.filter_by(doctor_id=doctor_id).count()
        active_cases   = Case.query.filter_by(doctor_id=doctor_id, status='active').count()
        total_patients = Patient.query.filter_by(doctor_id=doctor_id).count()

        return jsonify({
            'success': True,
            'doctor':  doctor.to_dict(),
            'stats': {
                'total_cases':    total_cases,
                'active_cases':   active_cases,
                'total_patients': total_patients,
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@profile_bp.route('/api/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    try:
        doctor_id = int(get_jwt_identity())
        doctor    = Doctor.query.get(doctor_id)

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        if 'name'           in data and data['name']:           doctor.name           = data['name'].strip()
        if 'specialty'      in data and data['specialty']:      doctor.specialty      = data['specialty'].strip()
        if 'phone'          in data and data['phone']:          doctor.phone          = data['phone'].strip()
        if 'license_number' in data and data['license_number']: doctor.license_number = data['license_number'].strip()

        if 'email' in data and data['email']:
            new_email = data['email'].strip().lower()
            if new_email != doctor.email:
                if Doctor.query.filter_by(email=new_email).first():
                    return jsonify({'error': 'Email already in use'}), 400
                doctor.email = new_email

        if 'new_password' in data:
            if not data.get('current_password'):
                return jsonify({'error': 'Current password is required'}), 400
            if not doctor.check_password(data['current_password']):
                return jsonify({'error': 'Current password is incorrect'}), 401
            if len(data['new_password']) < 8:
                return jsonify({'error': 'New password must be at least 8 characters'}), 400
            doctor.set_password(data['new_password'])

        db.session.commit()
        return jsonify({'success': True, 'doctor': doctor.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Patient
from datetime import datetime

patients_bp = Blueprint('patients', __name__)


@patients_bp.route('/api/patients', methods=['GET'])
@jwt_required()
def get_patients():
    try:
        doctor_id = int(get_jwt_identity())
        patients = Patient.query.filter_by(doctor_id=doctor_id).all()
        return jsonify({'success': True, 'data': [p.to_dict() for p in patients]}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@patients_bp.route('/api/patients/<string:patient_id>', methods=['GET'])
@jwt_required()
def get_patient(patient_id):
    try:
        doctor_id = int(get_jwt_identity())
        patient = Patient.query.filter_by(patient_id=patient_id, doctor_id=doctor_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        return jsonify({'success': True, 'data': patient.to_dict()}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@patients_bp.route('/api/patients', methods=['POST'])
@jwt_required()
def create_patient():
    try:
        doctor_id = int(get_jwt_identity())
        data = request.get_json()

        required = ['firstName', 'lastName', 'mrn', 'age', 'phone', 'gender']
        for field in required:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'}), 400

        last_patient = Patient.query.order_by(Patient.id.desc()).first()
        try:
            last_num = int(last_patient.patient_id.split('-')[1]) if last_patient else 0
        except Exception:
            last_num = 0
        patient_id = f"PT-{str(last_num + 1).zfill(3)}"

        new_patient = Patient(
            patient_id=patient_id,
            mrn=data['mrn'],
            first_name=data['firstName'],
            last_name=data['lastName'],
            age=int(data['age']),
            gender=data['gender'],
            phone=data['phone'],
            email=data.get('email', ''),
            condition=data.get('condition', ''),
            status=data.get('status', 'Active'),
            last_visit=datetime.now().date(),
            doctor_id=doctor_id,
        )

        db.session.add(new_patient)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Patient created successfully', 'data': new_patient.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@patients_bp.route('/api/patients/<string:patient_id>', methods=['PUT'])
@jwt_required()
def update_patient(patient_id):
    try:
        doctor_id = int(get_jwt_identity())
        patient = Patient.query.filter_by(patient_id=patient_id, doctor_id=doctor_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        data = request.get_json()
        if 'firstName'  in data: patient.first_name = data['firstName']
        if 'lastName'   in data: patient.last_name  = data['lastName']
        if 'mrn'        in data: patient.mrn        = data['mrn']
        if 'age'        in data: patient.age        = int(data['age'])
        if 'gender'     in data: patient.gender     = data['gender']
        if 'phone'      in data: patient.phone      = data['phone']
        if 'email'      in data: patient.email      = data['email']
        if 'condition'  in data: patient.condition  = data['condition']
        if 'status'     in data: patient.status     = data['status']

        db.session.commit()
        return jsonify({'success': True, 'data': patient.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@patients_bp.route('/api/patients/<string:patient_id>', methods=['PATCH'])
@jwt_required()
def patch_patient(patient_id):
    try:
        doctor_id = int(get_jwt_identity())
        patient = Patient.query.filter_by(patient_id=patient_id, doctor_id=doctor_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        data = request.get_json()
        if 'status'    in data: patient.status    = data['status']
        if 'condition' in data: patient.condition = data['condition']

        db.session.commit()
        return jsonify({'success': True, 'data': patient.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@patients_bp.route('/api/patients/<string:patient_id>', methods=['DELETE'])
@jwt_required()
def delete_patient(patient_id):
    try:
        doctor_id = int(get_jwt_identity())
        patient = Patient.query.filter_by(patient_id=patient_id, doctor_id=doctor_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        db.session.delete(patient)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Patient deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
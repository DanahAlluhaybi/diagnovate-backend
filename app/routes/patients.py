from flask import Blueprint, jsonify, request
from app.models import db, Patient
from datetime import datetime

patients_bp = Blueprint('patients', __name__)


# GET all patients
@patients_bp.route('/api/patients', methods=['GET'])
def get_patients():
    try:
        patients = Patient.query.all()
        return jsonify({
            'success': True,
            'data': [patient.to_dict() for patient in patients]
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# GET single patient
@patients_bp.route('/api/patients/<string:patient_id>', methods=['GET'])
def get_patient(patient_id):
    try:
        patient = Patient.query.filter_by(patient_id=patient_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        return jsonify({
            'success': True,
            'data': patient.to_dict()
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# POST new patient
@patients_bp.route('/api/patients', methods=['POST'])
def create_patient():
    try:
        data = request.get_json()
        print("Received data:", data)  # للتأكد من البيانات

        # Check required fields
        required = ['firstName', 'lastName', 'mrn', 'age', 'phone', 'gender']
        for field in required:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing field: {field}'
                }), 400

        # Generate patient ID
        last_patient = Patient.query.order_by(Patient.id.desc()).first()
        if last_patient and last_patient.patient_id:
            try:
                last_num = int(last_patient.patient_id.split('-')[1])
                new_num = last_num + 1
            except:
                new_num = 1
        else:
            new_num = 1
        patient_id = f"PT-{str(new_num).zfill(3)}"

        # Create new patient
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
            doctor_id=1  # افتراضي
        )

        db.session.add(new_patient)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Patient created successfully',
            'data': new_patient.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        print("Error:", str(e))  # للتصحيح
        return jsonify({'success': False, 'error': str(e)}), 500


# PUT update patient
@patients_bp.route('/api/patients/<string:patient_id>', methods=['PUT'])
def update_patient(patient_id):
    try:
        patient = Patient.query.filter_by(patient_id=patient_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        data = request.get_json()

        if 'firstName' in data:
            patient.first_name = data['firstName']
        if 'lastName' in data:
            patient.last_name = data['lastName']
        if 'mrn' in data:
            patient.mrn = data['mrn']
        if 'age' in data:
            patient.age = int(data['age'])
        if 'gender' in data:
            patient.gender = data['gender']
        if 'phone' in data:
            patient.phone = data['phone']
        if 'email' in data:
            patient.email = data['email']
        if 'condition' in data:
            patient.condition = data['condition']
        if 'status' in data:
            patient.status = data['status']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Patient updated successfully',
            'data': patient.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# DELETE patient
@patients_bp.route('/api/patients/<string:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    try:
        patient = Patient.query.filter_by(patient_id=patient_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        db.session.delete(patient)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Patient deleted successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
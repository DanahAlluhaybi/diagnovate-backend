from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Case, Patient
from datetime import datetime
import uuid

cases_bp = Blueprint('cases', __name__)


def generate_case_id() -> str:
    """Generate unique case ID like CASE-2024-A3F2"""
    return f"CASE-{datetime.now().year}-{uuid.uuid4().hex[:4].upper()}"


# ── GET all cases for logged-in doctor ───────────────────────────────────────
@cases_bp.route('/api/cases', methods=['GET'])
@jwt_required()
def get_cases():
    try:
        doctor_id  = int(get_jwt_identity())
        status     = request.args.get('status')
        patient_id = request.args.get('patient_id')

        query = Case.query.filter_by(doctor_id=doctor_id)
        if status:
            query = query.filter(Case.status == status)
        if patient_id:
            query = query.filter(Case.patient_id == int(patient_id))

        cases = query.order_by(Case.created_at.desc()).all()
        return jsonify({'success': True, 'data': [c.to_dict() for c in cases]}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── GET single case ───────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>', methods=['GET'])
@jwt_required()
def get_case(case_id):
    try:
        doctor_id = int(get_jwt_identity())
        case      = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'success': False, 'error': 'Case not found'}), 404
        return jsonify({'success': True, 'data': case.to_dict()}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── CREATE case ───────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases', methods=['POST'])
@jwt_required()
def create_case():
    try:
        doctor_id = int(get_jwt_identity())
        data      = request.get_json(force=True, silent=True)

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        if not data.get('patient_id'):
            return jsonify({'success': False, 'error': 'patient_id is required'}), 400

        # Verify patient belongs to this doctor
        patient = Patient.query.filter_by(id=data['patient_id'], doctor_id=doctor_id).first()
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404

        # Generate unique case_id
        case_id = generate_case_id()
        while Case.query.filter_by(case_id=case_id).first():
            case_id = generate_case_id()

        case = Case(
            case_id           = case_id,
            patient_id        = patient.id,
            doctor_id         = doctor_id,
            nodule_size       = data.get('nodule_size'),
            location          = data.get('location'),
            tirads_score      = data.get('tirads_score'),
            bethesda_category = data.get('bethesda_category'),
            symptoms          = data.get('symptoms'),
            diagnosis         = data.get('diagnosis'),
            notes             = data.get('notes'),
            status            = data.get('status', 'active'),
            image_path        = data.get('image_path'),
        )

        db.session.add(case)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Case created', 'data': case.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── UPDATE case ───────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>', methods=['PUT'])
@jwt_required()
def update_case(case_id):
    try:
        doctor_id = int(get_jwt_identity())
        case      = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'success': False, 'error': 'Case not found'}), 404

        data = request.get_json(force=True, silent=True) or {}

        if 'nodule_size'       in data: case.nodule_size       = data['nodule_size']
        if 'location'          in data: case.location          = data['location']
        if 'tirads_score'      in data: case.tirads_score      = data['tirads_score']
        if 'bethesda_category' in data: case.bethesda_category = data['bethesda_category']
        if 'symptoms'          in data: case.symptoms          = data['symptoms']
        if 'diagnosis'         in data: case.diagnosis         = data['diagnosis']
        if 'notes'             in data: case.notes             = data['notes']
        if 'status'            in data: case.status            = data['status']
        if 'image_path'        in data: case.image_path        = data['image_path']
        if 'enhanced_image_path' in data: case.enhanced_image_path = data['enhanced_image_path']

        case.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'data': case.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── PATCH case status ─────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>/status', methods=['PATCH'])
@jwt_required()
def update_case_status(case_id):
    try:
        doctor_id = int(get_jwt_identity())
        case      = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'success': False, 'error': 'Case not found'}), 404

        data = request.get_json(force=True, silent=True) or {}
        valid_statuses = ['active', 'completed', 'follow-up']
        new_status     = data.get('status')

        if not new_status or new_status not in valid_statuses:
            return jsonify({'success': False, 'error': f'Invalid status. Must be one of: {valid_statuses}'}), 400

        case.status     = new_status
        case.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'status': case.status}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── DELETE case ───────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>', methods=['DELETE'])
@jwt_required()
def delete_case(case_id):
    try:
        doctor_id = int(get_jwt_identity())
        case      = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'success': False, 'error': 'Case not found'}), 404

        db.session.delete(case)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Case deleted'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

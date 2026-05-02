from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Case, Patient
from datetime import datetime
import uuid

cases_bp = Blueprint('cases', __name__)


def _doctor_id() -> int:
    """Return doctor id as int (JWT identity is always str)."""
    return int(get_jwt_identity())


# ── LIST cases ─────────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases', methods=['GET'])
@jwt_required()
def get_cases():
    try:
        doctor_id    = _doctor_id()
        status_param = request.args.get('status')
        patient_param = request.args.get('patient_id')

        query = Case.query.filter_by(doctor_id=doctor_id)

        if status_param:
            query = query.filter(Case.status == status_param)
        if patient_param:
            patient = Patient.query.filter_by(
                patient_id=patient_param, doctor_id=doctor_id
            ).first()
            if patient:
                query = query.filter(Case.patient_id == patient.id)

        cases = query.order_by(Case.created_at.desc()).all()
        return jsonify({'success': True, 'data': [c.to_dict() for c in cases]}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── GET single case ────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>', methods=['GET'])
@jwt_required()
def get_case(case_id):
    try:
        doctor_id = _doctor_id()
        case = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'error': 'Case not found'}), 404
        return jsonify({'success': True, 'data': case.to_dict()}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── CREATE case ────────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases', methods=['POST'])
@jwt_required()
def create_case():
    try:
        doctor_id = _doctor_id()
        data      = request.get_json(force=True, silent=True)

        if not data:
            return jsonify({'error': 'No data provided'}), 400
        if not data.get('patient_id'):
            return jsonify({'error': 'patient_id is required'}), 400

        # Resolve patient
        patient = Patient.query.filter_by(
            patient_id=data['patient_id'], doctor_id=doctor_id
        ).first()
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        # Generate unique case ID
        case_id = f"CASE-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

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
        )

        # Update patient last_visit
        patient.last_visit = datetime.now().date()

        db.session.add(case)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Case created successfully',
            'data':    case.to_dict(),
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ── UPDATE case ────────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>', methods=['PUT'])
@jwt_required()
def update_case(case_id):
    try:
        doctor_id = _doctor_id()
        case = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'error': 'Case not found'}), 404

        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        editable = [
            'nodule_size', 'location', 'tirads_score',
            'bethesda_category', 'symptoms', 'diagnosis',
            'notes', 'status', 'image_path', 'enhanced_image_path',
        ]
        for field in editable:
            if field in data:
                setattr(case, field, data[field])

        case.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Case updated successfully',
            'data':    case.to_dict(),
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ── DELETE case ────────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>', methods=['DELETE'])
@jwt_required()
def delete_case(case_id):
    try:
        doctor_id = _doctor_id()
        case = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'error': 'Case not found'}), 404

        db.session.delete(case)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Case deleted successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ── PATCH status ───────────────────────────────────────────────────────────────
@cases_bp.route('/api/cases/<string:case_id>/status', methods=['PATCH'])
@jwt_required()
def update_case_status(case_id):
    try:
        doctor_id = _doctor_id()
        case = Case.query.filter_by(case_id=case_id, doctor_id=doctor_id).first()
        if not case:
            return jsonify({'error': 'Case not found'}), 404

        data   = request.get_json(force=True, silent=True) or {}
        status = data.get('status')
        if not status:
            return jsonify({'error': 'status field is required'}), 400

        case.status     = status
        case.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Case status updated to {status}',
            'status':  case.status,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
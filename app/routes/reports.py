from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import traceback
import uuid
from datetime import datetime

reports_bp = Blueprint('reports', __name__)


def _doctor_id() -> int:
    return int(get_jwt_identity())


_reports: dict = {}


def _make_report_id() -> str:
    return f"RPT-{uuid.uuid4().hex[:8].upper()}"


@reports_bp.route('/api/reports', methods=['POST', 'OPTIONS'])
@jwt_required()
def create_report():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        doctor_id = _doctor_id()
        data      = request.get_json(force=True, silent=True) or {}
        report_id = _make_report_id()
        report = {
            'report_id':  report_id,
            'doctor_id':  doctor_id,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            **data,
        }
        _reports[report_id] = report
        return jsonify({'success': True, 'message': 'Report created', 'data': report}), 201
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@reports_bp.route('/api/reports', methods=['GET'])
@jwt_required()
def list_reports():
    try:
        doctor_id  = _doctor_id()
        my_reports = sorted(
            [r for r in _reports.values() if r.get('doctor_id') == doctor_id],
            key=lambda r: r.get('created_at', ''), reverse=True
        )
        return jsonify({'success': True, 'data': my_reports}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@reports_bp.route('/api/reports/<string:report_id>', methods=['GET'])
@jwt_required()
def get_report(report_id: str):
    try:
        doctor_id = _doctor_id()
        report    = _reports.get(report_id)
        if not report or report.get('doctor_id') != doctor_id:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
        return jsonify({'success': True, 'data': report}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@reports_bp.route('/api/reports/<string:report_id>', methods=['PUT', 'OPTIONS'])
@jwt_required()
def update_report(report_id: str):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        doctor_id = _doctor_id()
        report    = _reports.get(report_id)
        if not report or report.get('doctor_id') != doctor_id:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
        data = request.get_json(force=True, silent=True) or {}
        report.update({**data, 'updated_at': datetime.utcnow().isoformat()})
        _reports[report_id] = report
        return jsonify({'success': True, 'data': report}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@reports_bp.route('/api/reports/<string:report_id>', methods=['DELETE'])
@jwt_required()
def delete_report(report_id: str):
    try:
        doctor_id = _doctor_id()
        report    = _reports.get(report_id)
        if not report or report.get('doctor_id') != doctor_id:
            return jsonify({'success': False, 'error': 'Report not found'}), 404
        del _reports[report_id]
        return jsonify({'success': True, 'message': 'Report deleted'}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@reports_bp.route('/api/report/generate', methods=['POST', 'OPTIONS'])
@jwt_required()
def generate_ai_report():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        from app.services.report_generation import generate_report
        case_data = request.get_json(force=True, silent=True) or {}
        if not case_data:
            return jsonify({'error': 'Case data is required'}), 400
        report_text = generate_report(case_data)
        return jsonify({'success': True, 'report': report_text}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

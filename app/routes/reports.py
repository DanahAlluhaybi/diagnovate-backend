from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.report_generation import generate_report
import traceback

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/api/report/generate', methods=['POST', 'OPTIONS'])
@jwt_required()
def generate_ai_report():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        case_data = request.get_json(force=True, silent=True) or {}
        if not case_data:
            return jsonify({'error': 'Case data is required'}), 400

        report_text = generate_report(case_data)
        return jsonify({'success': True, 'report': report_text}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

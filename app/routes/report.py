from flask import Blueprint, request, jsonify
from app.services.report_generation import generate_report as _generate_report

report_bp = Blueprint('report', __name__)

REQUIRED_FIELDS = {
    "patient_name":   "Patient Name",
    "patient_id":     "Patient ID",
    "gender":         "Gender",
    "date_of_diagnosis": "Date of Diagnosis",
    "lobe_involvement":  "Lobe Involvement",
    "tumor_size_cm":     "Tumor Size",
    "cancer_type":       "Cancer Type (Histopathological)",
    "t_stage":           "T Stage",
    "n_stage":           "N Stage",
    "m_stage":           "M Stage",
    "stage_group":       "Stage Group",
}

@report_bp.route('/api/reports/generate', methods=['POST'])
def generate_report():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validate required fields
        missing = [
            label for field, label in REQUIRED_FIELDS.items()
            if not data.get(field)
        ]
        if missing:
            return jsonify({
                'success': False,
                'error': 'Missing required fields',
                'missing_fields': missing
            }), 422

        report = _generate_report(data)
        return jsonify({'success': True, 'report': report}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Case, Patient
from datetime import date, timedelta

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/api/dashboard/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        doctor_id = int(get_jwt_identity())
        today     = date.today()

        active_cases   = Case.query.filter_by(doctor_id=doctor_id, status='active').count()
        urgent_cases   = Case.query.filter(
            Case.doctor_id == doctor_id,
            db.or_(
                Case.tirads_score >= 4,
                Case.bethesda_category.in_(['IV', 'V', 'VI'])
            )
        ).count()
        total_patients = Patient.query.filter_by(doctor_id=doctor_id).count()

        first_day       = date(today.year, today.month, 1)
        completed_cases = Case.query.filter(
            Case.doctor_id  == doctor_id,
            Case.status     == 'completed',
            Case.updated_at >= first_day
        ).count()

        return jsonify({
            'active_cases':    active_cases,
            'urgent_cases':    urgent_cases,
            'total_patients':  total_patients,
            'completed_cases': completed_cases,
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/recent-cases', methods=['GET'])
@jwt_required()
def get_recent_cases():
    try:
        doctor_id    = int(get_jwt_identity())
        recent_cases = Case.query.filter_by(doctor_id=doctor_id) \
            .order_by(Case.created_at.desc()).limit(10).all()
        return jsonify([case.to_dict() for case in recent_cases]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/cases-by-status', methods=['GET'])
@jwt_required()
def get_cases_by_status():
    try:
        doctor_id    = int(get_jwt_identity())
        cases        = Case.query.filter_by(doctor_id=doctor_id).all()
        status_count = {'active': 0, 'completed': 0, 'follow-up': 0}
        for case in cases:
            if case.status in status_count:
                status_count[case.status] += 1
        return jsonify(status_count), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

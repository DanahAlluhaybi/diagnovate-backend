from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Case, Patient
from datetime import date, datetime, timedelta
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)


def _doctor_id() -> int:
    return int(get_jwt_identity())


# ── STATS ──────────────────────────────────────────────────────────────────────
@dashboard_bp.route('/api/dashboard/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        doctor_id = _doctor_id()
        today     = date.today()

        # Active ultrasound cases
        active_cases = Case.query.filter_by(
            doctor_id=doctor_id, status='active'
        ).count()

        # Urgent cases: Bethesda III, IV, V, VI or TI-RADS 4–5
        urgent_cases = Case.query.filter(
            Case.doctor_id == doctor_id,
            db.or_(
                Case.bethesda_category.in_(['III', 'IV', 'V', 'VI']),
                Case.tirads_score >= 4,
            )
        ).count()

        # Total patients
        total_patients = Patient.query.filter_by(doctor_id=doctor_id).count()

        # Completed cases this month
        first_day = date(today.year, today.month, 1)
        completed_cases = Case.query.filter(
            Case.doctor_id == doctor_id,
            Case.status    == 'completed',
            Case.updated_at >= datetime.combine(first_day, datetime.min.time()),
        ).count()

        return jsonify({
            'active_cases':    active_cases,
            'urgent_cases':    urgent_cases,
            'total_patients':  total_patients,
            'completed_cases': completed_cases,
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── RECENT CASES ───────────────────────────────────────────────────────────────
@dashboard_bp.route('/api/dashboard/recent-cases', methods=['GET'])
@jwt_required()
def get_recent_cases():
    try:
        doctor_id = _doctor_id()
        cases = Case.query.filter_by(doctor_id=doctor_id) \
            .order_by(Case.created_at.desc()) \
            .limit(10).all()

        return jsonify([c.to_dict() for c in cases]), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── CASES BY STATUS ────────────────────────────────────────────────────────────
@dashboard_bp.route('/api/dashboard/cases-by-status', methods=['GET'])
@jwt_required()
def get_cases_by_status():
    try:
        doctor_id = _doctor_id()
        counts = {
            'active':    0,
            'completed': 0,
            'follow-up': 0,
        }
        for case in Case.query.filter_by(doctor_id=doctor_id).all():
            if case.status in counts:
                counts[case.status] += 1

        return jsonify(counts), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── TIRADS DISTRIBUTION ────────────────────────────────────────────────────────
@dashboard_bp.route('/api/dashboard/tirads-distribution', methods=['GET'])
@jwt_required()
def get_tirads_distribution():
    """Returns count of cases per TI-RADS score (1–5)."""
    try:
        doctor_id = _doctor_id()
        result = {}
        for score in range(1, 6):
            result[str(score)] = Case.query.filter_by(
                doctor_id=doctor_id, tirads_score=score
            ).count()

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
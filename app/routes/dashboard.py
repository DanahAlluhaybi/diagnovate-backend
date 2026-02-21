from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Case, Patient, Appointment
from datetime import date, datetime, timedelta
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/api/dashboard/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        doctor_id = get_jwt_identity()
        today = date.today()

        # Active cases
        active_cases = Case.query.filter_by(
            doctor_id=doctor_id,
            status='active'
        ).count()

        # Urgent cases (Bethesda III+)
        urgent_cases = Case.query.filter(
            Case.doctor_id == doctor_id,
            Case.bethesda_category.in_(['III', 'IV', 'V', 'VI'])
        ).count()

        # Total patients
        total_patients = Patient.query.filter_by(doctor_id=doctor_id).count()

        # Today's appointments
        today_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == today
        ).count()

        # Completed cases this month
        first_day = date(today.year, today.month, 1)
        completed_cases = Case.query.filter(
            Case.doctor_id == doctor_id,
            Case.status == 'completed',
            Case.updated_at >= first_day
        ).count()

        return jsonify({
            'active_cases': active_cases,
            'urgent_cases': urgent_cases,
            'total_patients': total_patients,
            'today_appointments': today_appointments,
            'completed_cases': completed_cases
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/recent-cases', methods=['GET'])
@jwt_required()
def get_recent_cases():
    try:
        doctor_id = get_jwt_identity()

        recent_cases = Case.query.filter_by(doctor_id=doctor_id) \
            .order_by(Case.created_at.desc()) \
            .limit(10) \
            .all()

        cases_list = [case.to_dict() for case in recent_cases]

        return jsonify(cases_list), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/weekly-appointments', methods=['GET'])
@jwt_required()
def get_weekly_appointments():
    try:
        doctor_id = get_jwt_identity()
        today = date.today()
        week_later = today + timedelta(days=7)

        appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date >= today,
            Appointment.appointment_date <= week_later
        ).order_by(Appointment.appointment_date, Appointment.appointment_time).all()

        result = {}
        for apt in appointments:
            date_str = apt.appointment_date.isoformat()
            if date_str not in result:
                result[date_str] = []
            result[date_str].append(apt.to_dict())

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/cases-by-status', methods=['GET'])
@jwt_required()
def get_cases_by_status():
    try:
        doctor_id = get_jwt_identity()

        cases = Case.query.filter_by(doctor_id=doctor_id).all()
        status_count = {
            'active': 0,
            'completed': 0,
            'follow-up': 0
        }

        for case in cases:
            if case.status in status_count:
                status_count[case.status] += 1

        return jsonify(status_count), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
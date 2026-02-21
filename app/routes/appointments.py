from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Appointment, Patient, Case
from datetime import datetime, date, timedelta
from sqlalchemy import or_

appointments_bp = Blueprint('appointments', __name__)


@appointments_bp.route('/api/appointments', methods=['GET'])
@jwt_required()
def get_appointments():
    try:
        doctor_id = get_jwt_identity()

        date_param = request.args.get('date')
        status_param = request.args.get('status')
        patient_param = request.args.get('patient')

        query = Appointment.query.filter_by(doctor_id=doctor_id)

        if date_param:
            query = query.filter(Appointment.appointment_date == date_param)
        if status_param:
            query = query.filter(Appointment.status == status_param)
        if patient_param:
            query = query.filter(
                or_(
                    Appointment.patient_name.ilike(f'%{patient_param}%'),
                    Appointment.patient_id_number.ilike(f'%{patient_param}%')
                )
            )

        appointments = query.order_by(
            Appointment.appointment_date.desc(),
            Appointment.appointment_time
        ).all()

        return jsonify([apt.to_dict() for apt in appointments]), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@appointments_bp.route('/api/appointments/today', methods=['GET'])
@jwt_required()
def get_today_appointments():
    try:
        doctor_id = get_jwt_identity()
        today = date.today()

        appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == today
        ).order_by(Appointment.appointment_time).all()

        return jsonify([apt.to_dict() for apt in appointments]), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@appointments_bp.route('/api/appointments', methods=['POST'])
@jwt_required()
def create_appointment():
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validation
        required_fields = ['patient_name', 'appointment_date', 'appointment_time']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing field: {field}'}), 400

        # Parse date and time
        try:
            appt_date = datetime.strptime(data['appointment_date'], '%Y-%m-%d').date()
            appt_time = datetime.strptime(data['appointment_time'], '%H:%M').time()
        except ValueError as e:
            return jsonify({'error': f'Invalid date or time format: {str(e)}'}), 400

        # Check if time slot is already booked
        existing = Appointment.query.filter_by(
            doctor_id=doctor_id,
            appointment_date=appt_date,
            appointment_time=appt_time,
            status='Confirmed'
        ).first()

        if existing:
            return jsonify({'error': 'This time slot is already booked'}), 400

        # Find existing patient or create new one
        patient = None
        patient_id_number = ''

        # First try to find by name under same doctor (avoid duplicate patients)
        existing_patient = Patient.query.filter_by(
            name=data['patient_name'],
            doctor_id=doctor_id
        ).first()

        if existing_patient:
            patient = existing_patient
            patient_id_number = patient.patient_id
        else:
            # Create new patient with unique ID
            patient_count = Patient.query.filter_by(doctor_id=doctor_id).count() + 1
            new_patient_id = f"PT-{datetime.now().year}{patient_count:04d}"

            # Make sure the generated ID is truly unique
            while Patient.query.filter_by(patient_id=new_patient_id).first():
                patient_count += 1
                new_patient_id = f"PT-{datetime.now().year}{patient_count:04d}"

            patient = Patient(
                patient_id=new_patient_id,
                name=data['patient_name'],
                phone=data.get('patient_phone'),
                doctor_id=doctor_id
            )
            db.session.add(patient)
            db.session.flush()
            patient_id_number = new_patient_id

        # Create appointment
        appointment = Appointment(
            patient_id=patient.id,
            patient_name=data['patient_name'],
            patient_phone=data.get('patient_phone', ''),
            patient_id_number=patient_id_number,
            appointment_date=appt_date,
            appointment_time=appt_time,
            appointment_type=data.get('appointment_type', 'Consultation'),
            duration=data.get('duration', 30),
            status=data.get('status', 'Pending'),
            case_id=data.get('case_id', ''),
            notes=data.get('notes', ''),
            doctor_id=doctor_id
        )

        db.session.add(appointment)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Appointment created successfully',
            'appointment': appointment.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@appointments_bp.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@jwt_required()
def update_appointment(appointment_id):
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json()

        appointment = Appointment.query.filter_by(
            id=appointment_id,
            doctor_id=doctor_id
        ).first()

        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404

        if data.get('patient_name'):
            appointment.patient_name = data['patient_name']
        if data.get('patient_phone'):
            appointment.patient_phone = data['patient_phone']
        if data.get('appointment_date'):
            appointment.appointment_date = datetime.strptime(data['appointment_date'], '%Y-%m-%d').date()
        if data.get('appointment_time'):
            appointment.appointment_time = datetime.strptime(data['appointment_time'], '%H:%M').time()
        if data.get('appointment_type'):
            appointment.appointment_type = data['appointment_type']
        if data.get('duration'):
            appointment.duration = data['duration']
        if data.get('status'):
            appointment.status = data['status']
        if data.get('notes'):
            appointment.notes = data['notes']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Appointment updated successfully',
            'appointment': appointment.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@appointments_bp.route('/api/appointments/<int:appointment_id>/status', methods=['PATCH'])
@jwt_required()
def update_appointment_status(appointment_id):
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json()

        appointment = Appointment.query.filter_by(
            id=appointment_id,
            doctor_id=doctor_id
        ).first()

        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404

        if 'status' in data:
            appointment.status = data['status']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Appointment status updated to {appointment.status}',
            'status': appointment.status
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@appointments_bp.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
@jwt_required()
def delete_appointment(appointment_id):
    try:
        doctor_id = get_jwt_identity()

        appointment = Appointment.query.filter_by(
            id=appointment_id,
            doctor_id=doctor_id
        ).first()

        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404

        db.session.delete(appointment)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Appointment deleted successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@appointments_bp.route('/api/appointments/check-availability', methods=['GET'])
@jwt_required()
def check_availability():
    try:
        doctor_id = get_jwt_identity()
        appointment_date = request.args.get('date')
        appointment_time = request.args.get('time')

        if not appointment_date or not appointment_time:
            return jsonify({'error': 'Date and time required'}), 400

        existing = Appointment.query.filter_by(
            doctor_id=doctor_id,
            appointment_date=datetime.strptime(appointment_date, '%Y-%m-%d').date(),
            appointment_time=datetime.strptime(appointment_time, '%H:%M').time(),
            status='Confirmed'
        ).first()

        return jsonify({'available': existing is None}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@appointments_bp.route('/api/appointments/stats', methods=['GET'])
@jwt_required()
def get_appointment_stats():
    try:
        doctor_id = get_jwt_identity()
        today = date.today()

        today_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == today
        ).all()

        today_completed = sum(1 for a in today_appointments if a.status == 'Completed')
        today_pending = sum(1 for a in today_appointments if a.status == 'Pending')
        today_confirmed = sum(1 for a in today_appointments if a.status == 'Confirmed')

        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        weekly_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date >= week_start,
            Appointment.appointment_date <= week_end
        ).count()

        month_start = date(today.year, today.month, 1)
        if today.month == 12:
            month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

        monthly_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date >= month_start,
            Appointment.appointment_date <= month_end
        ).count()

        return jsonify({
            'today': {
                'total': len(today_appointments),
                'completed': today_completed,
                'pending': today_pending,
                'confirmed': today_confirmed
            },
            'weekly': weekly_appointments,
            'monthly': monthly_appointments
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
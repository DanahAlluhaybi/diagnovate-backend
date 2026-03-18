
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Doctor, Admin
from datetime import datetime, date
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback

admin_bp = Blueprint('admin', __name__)




GMAIL_ADDRESS  = "your_project_email@gmail.com"   # ← إيميل المشروع
GMAIL_APP_PASS = "xxxx xxxx xxxx xxxx"             # ← الـ App Password
# ────────────────────────────────────────────────────────────

REJECTION_REASONS = [
    "The provided information is incorrect or incomplete.",
    "The license number is invalid or could not be verified.",
    "The stated specialty is not accepted on this platform.",
    "Other",
]


# ── Helper
def send_email(to_email: str, subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg['From']    = GMAIL_ADDRESS
        msg['To']      = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())

        print(f"📧 Email sent to {to_email}: {subject}")
    except Exception as e:
        print(f"⚠️ Failed to send email to {to_email}: {str(e)}")



def get_admin_or_error():
    try:
        admin_id = get_jwt_identity()
        admin    = Admin.query.get(int(admin_id))

        if not admin:
            return None, (jsonify({'error': 'Admin not found'}), 404)

        return admin, None
    except Exception as e:
        traceback.print_exc()
        return None, (jsonify({'error': str(e)}), 500)


# ── REJECTION REASONS ────────────────────────────────────────
@admin_bp.route('/api/admin/rejection-reasons', methods=['GET'])
@jwt_required()
def get_rejection_reasons():
    admin, err = get_admin_or_error()
    if err:
        return err
    return jsonify(REJECTION_REASONS)


# ── STATS ────────────────────────────────────────────────────
@admin_bp.route('/api/admin/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        today = date.today()

        total_users       = Doctor.query.count()
        pending_approvals = Doctor.query.filter_by(status='pending').count()
        active_users      = Doctor.query.filter_by(status='active').count()
        rejected_today    = Doctor.query.filter(
            Doctor.status == 'rejected',
            db.func.date(Doctor.created_at) == today
        ).count()

        return jsonify({
            'total_users': total_users,
            'pending_approvals': pending_approvals,
            'active_users': active_users,
            'rejected_today': rejected_today,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── PENDING USERS ────────────────────────────────────────────
@admin_bp.route('/api/admin/pending-users', methods=['GET'])
@jwt_required()
def get_pending():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        users  = Doctor.query.filter_by(status='pending').all()
        result = []
        for u in users:
            result.append({
                'id': u.id,
                'full_name': u.name,
                'email': u.email,
                'mobile': u.phone or '',
                'institution': '',
                'license_number': u.license_number or '',
                'specialty': u.specialty or 'Thyroid Specialist',
                'registered_at': u.created_at.isoformat() if u.created_at else '',
                'email_verified': True,
                'sms_verified': True,
            })

        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── ACTIVE / INACTIVE USERS ──────────────────────────────────
@admin_bp.route('/api/admin/active-users', methods=['GET'])
@jwt_required()
def get_active():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        users = Doctor.query.filter(
            Doctor.status.in_(['active', 'inactive'])
        ).all()

        result = []
        for u in users:
            result.append({
                'id': u.id,
                'full_name': u.name,
                'email': u.email,
                'institution': '',
                'specialty': u.specialty or 'Thyroid Specialist',
                'status': u.status,
                'last_login': u.created_at.isoformat() if u.created_at else '',
                'created_at': u.created_at.isoformat() if u.created_at else '',
            })

        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── APPROVE ──────────────────────────────────────────────────
@admin_bp.route('/api/admin/approve/<int:user_id>', methods=['POST'])
@jwt_required()
def approve(user_id):
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        user        = Doctor.query.get_or_404(user_id)
        user.status = 'active'
        db.session.commit()

        send_email(
            to_email=user.email,
            subject="Welcome to Diagnovate!",
            body=(
                f"Dear Dr. {user.name},\n\n"
                f"We are delighted to inform you that your account on Diagnovate "
                f"has been approved!\n\n"
                f"You can now log in and start using the platform.\n\n"
                f"Welcome aboard, and we look forward to supporting your work.\n\n"
                f"Best regards,\nDiagnovate Admin Team"
            )
        )

        print(f"✅ Approved: {user.name} (ID: {user_id})")
        return jsonify({'success': True, 'message': f'{user.name} approved successfully'})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── REJECT ───────────────────────────────────────────────────
@admin_bp.route('/api/admin/reject/<int:user_id>', methods=['POST'])
@jwt_required()
def reject(user_id):
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        data   = request.get_json() or {}
        reason = data.get('reason', '').strip()

        if reason == 'Other':
            custom = data.get('custom_reason', '').strip()
            reason = custom if custom else 'No reason provided'

        if not reason:
            return jsonify({'error': 'Rejection reason is required'}), 400

        user        = Doctor.query.get_or_404(user_id)
        user.status = 'rejected'
        db.session.commit()

        send_email(
            to_email=user.email,
            subject="Diagnovate - Registration Update",
            body=(
                f"Dear Dr. {user.name},\n\n"
                f"Thank you for your interest in joining Diagnovate.\n\n"
                f"After reviewing your registration, we regret to inform you "
                f"that your request has not been approved at this time.\n\n"
                f"Reason: {reason}\n\n"
                f"If you believe this is an error or have any questions, "
                f"please contact our support team.\n\n"
                f"Best regards,\nDiagnovate Admin Team"
            )
        )

        print(f"❌ Rejected: {user.name} (ID: {user_id}), reason: {reason}")
        return jsonify({'success': True, 'message': f'{user.name} rejected', 'reason': reason})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── ACTIVATE ─────
@admin_bp.route('/api/admin/activate/<int:user_id>', methods=['POST'])
@jwt_required()
def activate(user_id):
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        user        = Doctor.query.get_or_404(user_id)
        user.status = 'active'
        db.session.commit()

        print(f"✅ Activated: {user.name} (ID: {user_id})")
        return jsonify({'success': True, 'message': f'{user.name} activated'})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500



@admin_bp.route('/api/admin/deactivate/<int:user_id>', methods=['POST'])
@jwt_required()
def deactivate(user_id):
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        user        = Doctor.query.get_or_404(user_id)
        user.status = 'inactive'
        db.session.commit()

        print(f"⚠️ Deactivated: {user.name} (ID: {user_id})")
        return jsonify({'success': True, 'message': f'{user.name} deactivated'})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── DEBUG: ALL DOCTORS ───────────────────────────────────────
@admin_bp.route('/api/admin/debug/doctors', methods=['GET'])
@jwt_required()
def debug_doctors():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        doctors = Doctor.query.all()
        result  = [
            {
                'id': d.id,
                'name': d.name,
                'email': d.email,
                'status': d.status,
                'phone': d.phone,
                'license_number': d.license_number,
                'created_at': str(d.created_at) if d.created_at else None
            }
            for d in doctors
        ]

        return jsonify({
            'total': len(result),
            'doctors': result,
            'stats': {
                'pending':  Doctor.query.filter_by(status='pending').count(),
                'active':   Doctor.query.filter_by(status='active').count(),
                'inactive': Doctor.query.filter_by(status='inactive').count(),
                'rejected': Doctor.query.filter_by(status='rejected').count(),
            }
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── DEBUG: CHECK DB ──────────────────────────────────────────
@admin_bp.route('/api/admin/debug/check-db', methods=['GET'])
def check_db_public():
    try:
        from app import app
        import os

        db_uri  = app.config['SQLALCHEMY_DATABASE_URI']
        db_path = db_uri.replace('sqlite:///', '')

        if not os.path.isabs(db_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path  = os.path.join(base_dir, db_path)

        file_exists  = os.path.exists(db_path)
        file_size    = os.path.getsize(db_path) if file_exists else 0
        doctor_count = Doctor.query.count()
        admin_count  = Admin.query.count()

        return jsonify({
            'database_uri': db_uri,
            'database_path': db_path,
            'file_exists': file_exists,
            'file_size_bytes': file_size,
            'file_size_kb': round(file_size / 1024, 2) if file_exists else 0,
            'total_doctors': doctor_count,
            'total_admins': admin_count,
            'timestamp': str(datetime.now())
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
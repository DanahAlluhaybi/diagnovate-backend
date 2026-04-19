from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Doctor, Admin
from datetime import datetime, date
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback
import os

admin_bp = Blueprint('admin', __name__)

# ✅ FIX: load from .env instead of hardcoding
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")

REJECTION_REASONS = [
    "The provided information is incorrect or incomplete.",
    "The license number is invalid or could not be verified.",
    "The stated specialty is not accepted on this platform.",
    "Other",
]


# ── Helpers ───────────────────────────────────────────────────────────────
def send_email(to_email: str, subject: str, body: str):
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY", "").strip()
        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": to_email,
            "subject": subject,
            "html": f"<div style='font-family:Arial,sans-serif;padding:32px'>{body.replace(chr(10), '<br>')}</div>"
        })
        print(f"📧 Email sent to {to_email}")
    except Exception as e:
        print(f"⚠️ Failed to send email: {e}")


def get_admin_or_error():
    try:
        admin_id = get_jwt_identity()
        # ✅ FIX: check if it's an admin or a doctor calling admin endpoints
        admin = Admin.query.get(int(admin_id))
        if not admin:
            return None, (jsonify({'error': 'Admin not found or unauthorized'}), 403)
        return admin, None
    except Exception as e:
        traceback.print_exc()
        return None, (jsonify({'error': str(e)}), 500)


# ── Admin Login ───────────────────────────────────────────────────────────
@admin_bp.route('/api/admin/login', methods=['POST', 'OPTIONS'])
def admin_login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        from flask_jwt_extended import create_access_token
        from datetime import timedelta

        data     = request.get_json(force=True, silent=True)
        email    = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        admin = Admin.query.filter_by(email=email).first()
        if not admin or not admin.check_password(password):
            return jsonify({'error': 'Invalid admin credentials'}), 401

        access_token = create_access_token(
            identity=str(admin.id),
            expires_delta=timedelta(days=1)
        )
        return jsonify({
            'success':      True,
            'access_token': access_token,
            'admin':        admin.to_dict()
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Rejection Reasons ─────────────────────────────────────────────────────
@admin_bp.route('/api/admin/rejection-reasons', methods=['GET'])
@jwt_required()
def get_rejection_reasons():
    return jsonify(REJECTION_REASONS)


# ── Stats ─────────────────────────────────────────────────────────────────
@admin_bp.route('/api/admin/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        today = date.today()
        return jsonify({
            'total_users':       Doctor.query.count(),
            'pending_approvals': Doctor.query.filter_by(status='pending').count(),
            'active_users':      Doctor.query.filter_by(status='active').count(),
            'rejected_today':    Doctor.query.filter(
                Doctor.status == 'rejected',
                db.func.date(Doctor.created_at) == today
            ).count(),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Pending Users ─────────────────────────────────────────────────────────
@admin_bp.route('/api/admin/pending-users', methods=['GET'])
@jwt_required()
def get_pending():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        users = Doctor.query.filter_by(status='pending').all()
        return jsonify([{
            'id':             u.id,
            'full_name':      u.name,
            'email':          u.email,
            'mobile':         u.phone or '',
            'license_number': u.license_number or '',
            'specialty':      u.specialty or 'Thyroid Specialist',
            'registered_at':  u.created_at.isoformat() if u.created_at else '',
        } for u in users])
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Active Users ──────────────────────────────────────────────────────────
@admin_bp.route('/api/admin/active-users', methods=['GET'])
@jwt_required()
def get_active():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        users = Doctor.query.filter(Doctor.status.in_(['active', 'inactive'])).all()
        return jsonify([{
            'id':         u.id,
            'full_name':  u.name,
            'email':      u.email,
            'specialty':  u.specialty or 'Thyroid Specialist',
            'status':     u.status,
            'created_at': u.created_at.isoformat() if u.created_at else '',
        } for u in users])
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Approve ───────────────────────────────────────────────────────────────
@admin_bp.route('/api/admin/approve/<int:user_id>', methods=['POST'])
@jwt_required()
def approve(user_id):
    try:
        admin, err = get_admin_or_error()
        if err:
            return err

        user = Doctor.query.get_or_404(user_id)
        user.status = 'active'
        db.session.commit()

        send_email(
            to_email=user.email,
            subject="Welcome to Diagnovate!",
            body=(
                f"Dear Dr. {user.name},\n\n"
                f"Your Diagnovate account has been approved!\n"
                f"You can now log in and start using the platform.\n\n"
                f"Best regards,\nDiagnovate Admin Team"
            )
        )

        return jsonify({'success': True, 'message': f'{user.name} approved successfully'})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Reject ────────────────────────────────────────────────────────────────
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
            reason = data.get('custom_reason', '').strip() or 'No reason provided'
        if not reason:
            return jsonify({'error': 'Rejection reason is required'}), 400

        user        = Doctor.query.get_or_404(user_id)
        user.status = 'rejected'
        db.session.commit()

        send_email(
            to_email=user.email,
            subject="Diagnovate – Registration Update",
            body=(
                f"Dear Dr. {user.name},\n\n"
                f"Thank you for your interest in Diagnovate.\n"
                f"Unfortunately, your registration was not approved.\n\n"
                f"Reason: {reason}\n\n"
                f"If you have questions, please contact support.\n\n"
                f"Best regards,\nDiagnovate Admin Team"
            )
        )

        return jsonify({'success': True, 'message': f'{user.name} rejected', 'reason': reason})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Activate ──────────────────────────────────────────────────────────────
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
        return jsonify({'success': True, 'message': f'{user.name} activated'})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Deactivate ────────────────────────────────────────────────────────────
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
        return jsonify({'success': True, 'message': f'{user.name} deactivated'})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Debug: All Doctors ────────────────────────────────────────────────────
@admin_bp.route('/api/admin/debug/doctors', methods=['GET'])
@jwt_required()
def debug_doctors():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err
        doctors = Doctor.query.all()
        return jsonify({
            'total':   len(doctors),
            'doctors': [d.to_dict() for d in doctors],
            'stats':   {
                'pending':  Doctor.query.filter_by(status='pending').count(),
                'active':   Doctor.query.filter_by(status='active').count(),
                'inactive': Doctor.query.filter_by(status='inactive').count(),
                'rejected': Doctor.query.filter_by(status='rejected').count(),
            }
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/admin/create-first-admin', methods=['POST'])
def create_first_admin():
    from app.models import Admin
    if Admin.query.count() > 0:
        return jsonify({'error': 'Admin already exists'}), 400
    admin = Admin(name="Admin", email="admin@diagnovate.org")
    admin.set_password("Admin@1234")
    db.session.add(admin)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Admin created'})

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Doctor, Admin
from app.routes.auth import _email_html_wrapper as _admin_email_html
from datetime import datetime, date
import traceback
import os

admin_bp = Blueprint('admin', __name__)

REJECTION_REASONS = [
    "The provided information is incorrect or incomplete.",
    "The license number is invalid or could not be verified.",
    "The stated specialty is not accepted on this platform.",
    "Other",
]


def send_email(to_email: str, subject: str, html_content: str):
    """Send a transactional email via Resend. Logs failures without raising."""
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY", "").strip()
        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": to_email,
            "subject": subject,
            "html": html_content,
        })
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def get_admin_or_error():
    """Resolve the JWT identity to an Admin record, returning (admin, None) or (None, error_response)."""
    try:
        from flask_jwt_extended import get_jwt
        admin_id = get_jwt_identity()
        claims   = get_jwt()
        if claims.get('role') != 'admin':
            return None, (jsonify({'error': 'Admin not found or unauthorized'}), 403)
        admin = Admin.query.get(int(admin_id))
        if not admin:
            return None, (jsonify({'error': 'Admin not found or unauthorized'}), 403)
        return admin, None
    except Exception as e:
        traceback.print_exc()
        return None, (jsonify({'error': str(e)}), 500)


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
            additional_claims={'role': 'admin'},
            expires_delta=timedelta(hours=8)
        )
        return jsonify({
            'success':      True,
            'access_token': access_token,
            'admin':        admin.to_dict()
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/admin/rejection-reasons', methods=['GET'])
@jwt_required()
def get_rejection_reasons():
    return jsonify(REJECTION_REASONS)


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
            subject="Diagnovate – Your Account Has Been Approved",
            html_content=_admin_email_html(f"""
    <h2 style="color:#111827;margin:0 0 8px">Your account is approved!</h2>
    <p style="color:#6b7280;margin:0 0 16px">Congratulations, Dr. {user.name}.</p>
    <p style="color:#6b7280;margin:0 0 32px">Your Diagnovate account has been reviewed and approved. You can now log in and start using the platform.</p>
    <div style="text-align:center">
      <a href="https://diagnovate.org/log-in?role=doctor" style="background:#0D9488;color:#ffffff;padding:14px 32px;text-decoration:none;border-radius:8px;font-weight:600;font-size:15px;display:inline-block">Log In Now</a>
    </div>""")
        )

        return jsonify({'success': True, 'message': f'{user.name} approved successfully'})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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
            html_content=_admin_email_html(f"""
    <h2 style="color:#111827;margin:0 0 8px">Registration not approved</h2>
    <p style="color:#6b7280;margin:0 0 16px">Dear Dr. {user.name},</p>
    <p style="color:#6b7280;margin:0 0 24px">Thank you for your interest in Diagnovate. Unfortunately, your registration was not approved at this time.</p>
    <div style="background:#fef2f2;border-left:4px solid #ef4444;border-radius:4px;padding:16px 20px;margin:0 0 24px">
      <p style="color:#374151;margin:0"><strong>Reason:</strong> {reason}</p>
    </div>
    <p style="color:#6b7280;margin:0">If you believe this is an error or have questions, please contact our support team.</p>""")
        )

        return jsonify({'success': True, 'message': f'{user.name} rejected', 'reason': reason})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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


@admin_bp.route('/api/admin/change-password', methods=['POST'])
@jwt_required()
def change_password():
    try:
        admin, err = get_admin_or_error()
        if err:
            return err
        data             = request.get_json(force=True, silent=True) or {}
        current_password = data.get('current_password', '')
        new_password     = data.get('new_password', '')
        if not current_password or not new_password:
            return jsonify({'error': 'Current and new password are required'}), 400
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if not admin.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401
        admin.set_password(new_password)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Password changed successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

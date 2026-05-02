from flask import Blueprint, request, jsonify
from app.models import db, Doctor, PasswordResetToken
from app.routes.auth import _email_html_wrapper
import resend, os, secrets
from datetime import datetime, timedelta

forgot_password_bp = Blueprint('forgot_password', __name__)
resend.api_key = os.getenv("RESEND_API_KEY", "").strip()
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://diagnovate.org")


@forgot_password_bp.route('/api/auth/forgot-password', methods=['POST', 'OPTIONS'])
def forgot_password():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True) or {}
        email = data.get('email', '').strip().lower()
        if not email:
            return jsonify({'error': 'Email is required'}), 400

        doctor = Doctor.query.filter_by(email=email).first()
        if not doctor:
            # لا نكشف إذا الإيميل موجود أو لا (أمان)
            return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200

        # احذف الـ tokens القديمة لنفس الإيميل
        PasswordResetToken.query.filter_by(email=email).delete()
        db.session.commit()

        token = secrets.token_urlsafe(32)
        db.session.add(PasswordResetToken(
            email=email,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        ))
        db.session.commit()

        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"

        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": email,
            "subject": "Diagnovate – Reset Your Password",
            "html": _email_html_wrapper(f"""
    <h2 style="color:#111827;margin:0 0 8px">Reset your password</h2>
    <p style="color:#6b7280;margin:0 0 32px">Hi Dr. {doctor.name}, click the button below to choose a new password.</p>
    <div style="text-align:center;margin:0 0 32px">
      <a href="{reset_link}" style="background:#0D9488;color:#ffffff;padding:14px 32px;text-decoration:none;border-radius:8px;font-weight:600;font-size:15px;display:inline-block;letter-spacing:0.3px">Reset Password</a>
    </div>
    <p style="color:#6b7280;text-align:center;font-size:14px;margin:0">This link expires in <strong>1 hour</strong>.</p>"""),
        })
        return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@forgot_password_bp.route('/api/auth/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True) or {}
        token    = data.get('token', '').strip()
        password = data.get('password', '')

        if not token or not password:
            return jsonify({'error': 'Token and password are required'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        # احذف الـ tokens المنتهية أولاً
        PasswordResetToken.query.filter(PasswordResetToken.expires_at < datetime.utcnow()).delete()
        db.session.commit()

        entry = PasswordResetToken.query.filter_by(token=token, used=False).first()
        if not entry:
            return jsonify({'error': 'Invalid or expired reset link'}), 400

        doctor = Doctor.query.filter_by(email=entry.email).first()
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        doctor.set_password(password)
        entry.used = True
        db.session.commit()

        return jsonify({'success': True, 'message': 'Password reset successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
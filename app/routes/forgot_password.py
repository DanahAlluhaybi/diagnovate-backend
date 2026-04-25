from flask import Blueprint, request, jsonify
from app.models import db, Doctor
import resend, os, secrets
from datetime import datetime, timedelta

forgot_password_bp = Blueprint('forgot_password', __name__)
resend.api_key = os.getenv("RESEND_API_KEY", "").strip()
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://diagnovate.org")

_reset_tokens = {}

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
            return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200
        token = secrets.token_urlsafe(32)
        _reset_tokens[token] = {'email': email, 'expires': datetime.utcnow() + timedelta(hours=1)}
        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": email,
            "subject": "Diagnovate – Reset Your Password",
            "html": f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#ffffff">
  <div style="background:#0D9488;padding:24px 32px;border-radius:8px 8px 0 0">
    <h1 style="color:white;margin:0;font-size:24px;letter-spacing:1px">Diagnovate</h1>
  </div>
  <div style="padding:40px 32px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px">
    <h2 style="color:#111827;margin:0 0 8px">Reset your password</h2>
    <p style="color:#6b7280;margin:0 0 32px">Hi Dr. {doctor.name}, click the button below to choose a new password.</p>
    <div style="text-align:center;margin:0 0 32px">
      <a href="{reset_link}" style="background:#0D9488;color:white;padding:14px 32px;text-decoration:none;border-radius:6px;font-weight:600;font-size:15px">Reset Password</a>
    </div>
    <p style="color:#6b7280;text-align:center;font-size:14px;margin:0">This link expires in <strong>1 hour</strong>.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:32px 0">
    <p style="color:#9ca3af;font-size:12px;margin:0">Diagnovate &mdash; AI-powered thyroid diagnosis platform.<br>If you did not request this email, you can safely ignore it.</p>
  </div>
</div>"""
        })
        return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@forgot_password_bp.route('/api/auth/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json(force=True, silent=True) or {}
        token = data.get('token', '').strip()
        password = data.get('password', '')
        if not token or not password:
            return jsonify({'error': 'Token and password are required'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        entry = _reset_tokens.get(token)
        if not entry:
            return jsonify({'error': 'Invalid or expired reset link'}), 400
        if datetime.utcnow() > entry['expires']:
            _reset_tokens.pop(token, None)
            return jsonify({'error': 'Reset link has expired'}), 400
        doctor = Doctor.query.filter_by(email=entry['email']).first()
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404
        doctor.set_password(password)
        db.session.commit()
        _reset_tokens.pop(token, None)
        return jsonify({'success': True, 'message': 'Password reset successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

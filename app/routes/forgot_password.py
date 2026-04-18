from flask import Blueprint, request, jsonify
from app.models import Doctor
import resend
import os

forgot_password_bp = Blueprint('forgot_password', __name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://diagnovate.org")


@forgot_password_bp.route('/api/auth/forgot-password', methods=['POST', 'OPTIONS'])
def forgot_password():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    try:
        data  = request.get_json(force=True, silent=True)
        email = data.get('email', '').strip().lower() if data else ''

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        doctor = Doctor.query.filter_by(email=email).first()
        # Security: don't reveal if email exists or not
        if not doctor:
            return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200

        if not resend.api_key:
            print("⚠️ RESEND_API_KEY not set")
            return jsonify({'error': 'Email service not configured'}), 500

        reset_link = f"{FRONTEND_URL}/reset-password?email={email}"

        resend.Emails.send({
            "from": "noreply@diagnovate.org",
            "to": email,
            "subject": "Diagnovate – Reset Your Password",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #0066CC; padding: 24px; border-radius: 8px 8px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 24px;">Diagnovate</h1>
                </div>
                <div style="padding: 32px; border: 1px solid #e0e0e0; border-radius: 0 0 8px 8px;">
                    <h2 style="color: #333;">Password Reset Request</h2>
                    <p style="color: #555;">Dear Dr. {doctor.name},</p>
                    <p style="color: #555;">We received a request to reset your Diagnovate password. Click the button below to proceed:</p>
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{reset_link}" style="
                            background-color: #0066CC;
                            color: white;
                            padding: 14px 32px;
                            text-decoration: none;
                            border-radius: 6px;
                            display: inline-block;
                            font-weight: bold;
                            font-size: 16px;
                        ">Reset Password</a>
                    </div>
                    <p style="color: #888; font-size: 14px;">⏱ This link will expire in <strong>1 hour</strong>.</p>
                    <p style="color: #888; font-size: 14px;">If you didn't request this, you can safely ignore this email.</p>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
                    <p style="color: #aaa; font-size: 12px;">Best regards,<br>Diagnovate Team</p>
                </div>
            </div>
            """
        })

        print(f"📧 Password reset email sent to {email}")
        return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200

    except Exception as e:
        print(f"❌ ERROR in forgot_password: {str(e)}")
        return jsonify({'error': str(e)}), 500
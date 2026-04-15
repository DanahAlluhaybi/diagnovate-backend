from flask import Blueprint, request, jsonify
from app.models import Doctor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import os

# ✅ FIX: was incorrectly using auth_bp — needs its own blueprint
forgot_password_bp = Blueprint('forgot_password', __name__)

GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")


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
        # ✅ Security: don't reveal if email exists or not
        if not doctor:
            return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200

        if not GMAIL_ADDRESS or not GMAIL_APP_PASS:
            print("⚠️ GMAIL_ADDRESS or GMAIL_APP_PASS not set in .env")
            return jsonify({'error': 'Email service not configured'}), 500

        reset_link = f"http://localhost:3000/reset-password?email={email}"

        msg             = MIMEMultipart()
        msg["From"]     = GMAIL_ADDRESS
        msg["To"]       = email
        msg["Subject"]  = "Diagnovate – Reset Your Password"

        body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px;">
            <h2>Password Reset Request</h2>
            <p>Dear Dr. {doctor.name},</p>
            <p>We received a request to reset your Diagnovate password.</p>
            <p>
                <a href="{reset_link}" style="
                    background-color: #0066CC;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 6px;
                    display: inline-block;
                ">Reset Password</a>
            </p>
            <p>If you didn't request this, please ignore this email.</p>
            <p>This link will expire in 1 hour.</p>
            <br>
            <p>Best regards,<br>Diagnovate Team</p>
        </div>
        """
        msg.attach(MIMEText(body, "html"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        server.sendmail(GMAIL_ADDRESS, email, msg.as_string())
        server.quit()

        print(f"📧 Password reset email sent to {email}")
        return jsonify({'success': True, 'message': 'If this email is registered, a reset link has been sent'}), 200

    except smtplib.SMTPAuthenticationError:
        print("❌ Gmail authentication failed — check GMAIL_APP_PASS in .env")
        return jsonify({'error': 'Email service authentication failed'}), 500
    except Exception as e:
        print(f"❌ ERROR in forgot_password: {str(e)}")
        return jsonify({'error': str(e)}), 500

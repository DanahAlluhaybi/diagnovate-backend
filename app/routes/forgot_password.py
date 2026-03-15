
from flask import Blueprint, request, jsonify
from app.models import db, Doctor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import os

# راوت نسيت كلمة المرور
@auth_bp.route('/api/auth/forgot-password', methods=['POST', 'OPTIONS'])
def forgot_password():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    try:
        data = request.get_json()
        email = data.get('email', '').strip()

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        # تحقق من وجود الإيميل في قاعدة البيانات
        doctor = Doctor.query.filter_by(email=email).first()
        if not doctor:
            return jsonify({'error': 'Email not found'}), 404

        # إعداد بيانات الإيميل (من و إلى)
        sender_email = os.getenv("MAIL_USER")
        sender_password = os.getenv("MAIL_PASS")

        # تحقق إذا كانت بيانات الإيميل في .env موجودة
        if not sender_email or not sender_password:
            return jsonify({'error': 'Mail settings are missing'}), 500

        reset_link = f"http://localhost:5000/reset-password?email={email}"

        # إعداد الرسالة
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = email
        msg["Subject"] = "Reset your password"

        body = f"""
        <h3>Password Reset</h3>
        <p>Click the link below to reset your password:</p>
        <a href="{reset_link}">Reset Password</a>
        """
        msg.attach(MIMEText(body, "html"))

        # إرسال الإيميل
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, email, msg.as_string())
        server.quit()

        return jsonify({
            'success': True,
            'message': 'Reset email sent successfully'
        }), 200

    except Exception as e:
        print(f"ERROR in forgot_password: {str(e)}")
        return jsonify({'error': str(e)}), 500
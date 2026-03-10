from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Doctor, Case, Patient

print("✅ Profile blueprint loaded!")

profile_bp = Blueprint('profile', __name__)


# Route للاختبار
@profile_bp.route('/api/test', methods=['GET'])
def test():
    return jsonify({'message': 'Profile route is working!'}), 200


# GET: جلب الملف الشخصي
@profile_bp.route('/api/profile', methods=['GET'])
@jwt_required()
def get_profile():
    try:
        doctor_id = get_jwt_identity()
        doctor = Doctor.query.get(doctor_id)

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        # إحصائيات
        total_cases = Case.query.filter_by(doctor_id=doctor_id).count()
        active_cases = Case.query.filter_by(doctor_id=doctor_id, status='active').count()
        total_patients = Patient.query.filter_by(doctor_id=doctor_id).count()

        return jsonify({
            'success': True,
            'doctor': doctor.to_dict(),
            'stats': {
                'total_cases': total_cases,
                'active_cases': active_cases,
                'total_patients': total_patients,
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# PUT: تحديث الملف الشخصي
@profile_bp.route('/api/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    try:
        print("\n" + "="*60)
        print("🟢 PROFILE UPDATE ENDPOINT HIT")
        print("="*60)

        doctor_id = get_jwt_identity()
        print(f"🟢 Doctor ID: {doctor_id}")

        doctor = Doctor.query.get(doctor_id)
        print(f"🟢 Doctor found: {doctor is not None}")

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        # البيانات الخام
        raw_data = request.get_data(as_text=True)
        print(f"🟢 Raw request data: {raw_data}")

        data = request.get_json()
        print(f"🟢 Parsed JSON data: {data}")

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # تحديث الحقول المسموح بها
        if 'name' in data and data['name']:
            doctor.name = data['name'].strip()

        if 'specialty' in data and data['specialty']:
            doctor.specialty = data['specialty'].strip()

        if 'phone' in data and data['phone']:
            doctor.phone = data['phone'].strip()

        if 'license_number' in data and data['license_number']:
            doctor.license_number = data['license_number'].strip()

        # تغيير الإيميل
        if 'email' in data and data['email']:
            new_email = data['email'].strip()
            if new_email != doctor.email:
                existing = Doctor.query.filter_by(email=new_email).first()
                if existing:
                    return jsonify({'error': 'Email already in use'}), 400
                doctor.email = new_email

        # تغيير كلمة المرور
        if 'new_password' in data:
            if not data.get('current_password'):
                return jsonify({'error': 'Current password is required'}), 400
            if not doctor.check_password(data['current_password']):
                return jsonify({'error': 'Current password is incorrect'}), 401
            if len(data['new_password']) < 6:
                return jsonify({'error': 'New password must be at least 6 characters'}), 400
            doctor.set_password(data['new_password'])

        db.session.commit()
        print("✅ Database commit successful!")

        return jsonify({
            'success': True,
            'doctor': doctor.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ ERROR: {str(e)}")
        return jsonify({'error': str(e)}), 500
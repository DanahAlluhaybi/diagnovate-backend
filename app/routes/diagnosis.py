from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import joblib
import numpy as np
import os

diagnosis_bp = Blueprint('diagnosis', __name__)

# ── تحميل الموديل عند بدء السيرفر ──
MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'ml')

try:
    model           = joblib.load(os.path.join(MODEL_DIR, 'thyroid_model.pkl'))
    label_encoders  = joblib.load(os.path.join(MODEL_DIR, 'label_encoders.pkl'))
    feature_columns = joblib.load(os.path.join(MODEL_DIR, 'feature_columns.pkl'))
    print("✅ Thyroid model loaded successfully")
except Exception as e:
    model = None
    print(f"⚠️ Could not load model: {e}")


@diagnosis_bp.route('/api/diagnosis/predict', methods=['POST', 'OPTIONS'])
@jwt_required()
def predict():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if model is None:
        return jsonify({'error': 'Model not loaded. Please train the model first.'}), 500

    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # ── بناء الـ input من القيم المُرسلة ──
        input_values = []
        missing = []

        for col in feature_columns:
            val = data.get(col)
            if val is None:
                missing.append(col)
            else:
                # تحويل القيم النصية إذا كان العمود يحتاج encoding
                if col in label_encoders:
                    try:
                        val = label_encoders[col].transform([str(val)])[0]
                    except Exception:
                        val = 0
                input_values.append(float(val))

        if missing:
            return jsonify({
                'error': f'Missing fields: {missing}',
                'required_fields': feature_columns
            }), 400

        input_array = np.array([input_values])
        prediction  = model.predict(input_array)[0]
        probability = model.predict_proba(input_array)[0]

        # ── تحويل النتيجة لنص مفهوم ──
        target_encoder = label_encoders.get('target') or label_encoders.get('diagnosis') or label_encoders.get('class')

        if target_encoder:
            label = target_encoder.inverse_transform([int(prediction)])[0]
        else:
            label = str(prediction)

        # ── تصنيف النتيجة ──
        label_lower = str(label).lower()
        if 'negative' in label_lower or 'normal' in label_lower or label_lower == '0':
            status   = 'Normal'
            severity = 'low'
        elif 'hypo' in label_lower:
            status   = 'Hypothyroidism'
            severity = 'high'
        elif 'hyper' in label_lower:
            status   = 'Hyperthyroidism'
            severity = 'high'
        else:
            status   = label
            severity = 'medium'

        return jsonify({
            'success':    True,
            'diagnosis':  status,
            'raw_label':  label,
            'confidence': round(float(max(probability)) * 100, 2),
            'severity':   severity,
            'probabilities': {
                str(i): round(float(p) * 100, 2)
                for i, p in enumerate(probability)
            }
        }), 200

    except Exception as e:
        print(f"ERROR in predict: {str(e)}")
        return jsonify({'error': str(e)}), 500


@diagnosis_bp.route('/api/diagnosis/fields', methods=['GET'])
@jwt_required()
def get_fields():
    """يرجع قائمة الـ fields المطلوبة للتشخيص"""
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 500
    return jsonify({
        'success': True,
        'required_fields': feature_columns
    }), 200
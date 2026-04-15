from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import numpy as np
import pandas as pd
import os

diagnosis_bp = Blueprint('diagnosis', __name__)

# ── تحميل المودل عند بدء السيرفر ──
MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'ml')
MODEL_PATH = os.path.join(MODEL_DIR, 'thyroid_model.pkl')
FEATURES_PATH = os.path.join(MODEL_DIR, 'feature_columns.pkl')
ENCODERS_PATH = os.path.join(MODEL_DIR, 'label_encoders.pkl')

model = None
feature_columns = None
label_encoders = None

def load_model():
    global model, feature_columns, label_encoders
    try:
        import joblib
        model = joblib.load(MODEL_PATH)
        feature_columns = joblib.load(FEATURES_PATH)
        label_encoders = joblib.load(ENCODERS_PATH)
        print("✅ Thyroid model loaded successfully")
        return True
    except Exception as e:
        print(f"⚠️ Could not load model: {e}")
        return False

# تحميل المودل مباشرة
load_model()


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

        # ── تحويل المدخلات إلى DataFrame ──
        input_df = pd.DataFrame([data])

        # ── التأكد من وجود جميع الأعمدة المطلوبة ──
        for col in feature_columns:
            if col not in input_df.columns:
                input_df[col] = np.nan

        # ── تطبيق نفس preprocessing اللي سويناه في التدريب ──
        # 1. تحويل الأعمدة الرقمية
        for col in input_df.columns:
            if col == 'target':
                continue
            try:
                input_df[col] = pd.to_numeric(input_df[col])
            except (ValueError, TypeError):
                pass

        # 2. تعبئة القيم الناقصة (نفس طريقة التدريب)
        for col in input_df.columns:
            if col == 'target':
                continue
            if input_df[col].dtype in ['float64', 'int64']:
                # نستخدم median زي ما سوينا في التدريب
                input_df[col] = input_df[col].fillna(input_df[col].median())
            else:
                # نستخدم mode للأعمدة النصية
                mode_val = input_df[col].mode()
                if not mode_val.empty:
                    input_df[col] = input_df[col].fillna(mode_val[0])
                else:
                    input_df[col] = input_df[col].fillna('f')

        # 3. تطبيق Label Encoding للأعمدة النصية
        for col in label_encoders:
            if col == 'target':
                continue
            if col in input_df.columns:
                le = label_encoders[col]
                # التعامل مع القيم الجديدة غير المرئية
                def encode_value(x):
                    try:
                        return le.transform([str(x)])[0]
                    except:
                        return -1  # قيمة افتراضية للقيم الجديدة
                input_df[col] = input_df[col].apply(encode_value)

        # 4. ترتيب الأعمدة حسب feature_columns
        input_df = input_df[feature_columns]

        # 5. التأكد من عدم وجود قيم None
        input_df = input_df.fillna(0)

        # ── التنبؤ ──
        prediction = model.predict(input_df)[0]
        probability = model.predict_proba(input_df)[0]

        # ── تحويل النتيجة لنص مفهوم ──
        target_encoder = label_encoders.get('target')
        if target_encoder:
            label = target_encoder.inverse_transform([int(prediction)])[0]
        else:
            label = str(prediction)

        # ── تصنيف النتيجة ──
        label_lower = str(label).lower()
        if 'normal' in label_lower:
            status = 'Normal'
            severity = 'low'
        elif 'hypo' in label_lower:
            status = 'Hypothyroidism'
            severity = 'high'
        elif 'hyper' in label_lower:
            status = 'Hyperthyroidism'
            severity = 'high'
        else:
            status = label
            severity = 'medium'

        # تحويل الاحتمالات إلى نسب مئوية
        prob_dict = {}
        for i, p in enumerate(probability):
            class_name = target_encoder.inverse_transform([i])[0] if target_encoder else str(i)
            prob_dict[class_name] = round(float(p) * 100, 2)

        return jsonify({
            'success': True,
            'diagnosis': status,
            'raw_label': label,
            'confidence': round(float(max(probability)) * 100, 2),
            'severity': severity,
            'probabilities': prob_dict
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
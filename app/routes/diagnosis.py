from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import joblib
import numpy as np
import os

diagnosis_bp = Blueprint('diagnosis', __name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'ml')

try:
    model           = joblib.load(os.path.join(MODEL_DIR, 'thyroid_model.pkl'))
    label_encoders  = joblib.load(os.path.join(MODEL_DIR, 'label_encoders.pkl'))
    feature_columns = joblib.load(os.path.join(MODEL_DIR, 'feature_columns.pkl'))
    model_name      = type(model).__name__
    print(f"✅ Thyroid model loaded: {model_name}")
except Exception as e:
    model           = None
    label_encoders  = {}
    feature_columns = []
    model_name      = 'Unknown'
    print(f"⚠️ Could not load model: {e}")


# ── PREDICT ────────────────────────────────────────────────────────────────────
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

        # ── Build input vector ─────────────────────────────────
        # FIX: null values → default 0.0 instead of rejecting the whole request
        input_values = []
        for col in feature_columns:
            val = data.get(col)
            if val is None:
                input_values.append(0.0)
            else:
                if col in label_encoders:
                    try:
                        val = label_encoders[col].transform([str(val)])[0]
                    except Exception:
                        val = 0
                try:
                    input_values.append(float(val))
                except (TypeError, ValueError):
                    input_values.append(0.0)

        input_array = np.array([input_values])
        prediction  = model.predict(input_array)[0]
        probability = model.predict_proba(input_array)[0]

        # ── Decode label ───────────────────────────────────────
        target_encoder = (
            label_encoders.get('target')
            or label_encoders.get('diagnosis')
            or label_encoders.get('class')
        )

        label = (
            target_encoder.inverse_transform([int(prediction)])[0]
            if target_encoder
            else str(prediction)
        )

        # ── Classify severity ──────────────────────────────────
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

        confidence = round(float(max(probability)) * 100, 2)

        # Build probability map with class names if available
        if target_encoder and hasattr(target_encoder, 'classes_'):
            prob_map = {
                str(cls): round(float(p) * 100, 2)
                for cls, p in zip(target_encoder.classes_, probability)
            }
        else:
            prob_map = {
                str(i): round(float(p) * 100, 2)
                for i, p in enumerate(probability)
            }

        return jsonify({
            'success':       True,
            'diagnosis':     status,
            'raw_label':     label,
            'confidence':    confidence,
            'severity':      severity,
            'model_used':    model_name,   # FIX: added model_used so frontend can display real model
            'probabilities': prob_map,
        }), 200

    except Exception as e:
        print(f"ERROR in predict: {e}")
        return jsonify({'error': str(e)}), 500


# ── GET required fields ────────────────────────────────────────────────────────
@diagnosis_bp.route('/api/diagnosis/fields', methods=['GET'])
@jwt_required()
def get_fields():
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 500
    return jsonify({
        'success':         True,
        'required_fields': feature_columns,
        'model_name':      model_name,
    }), 200
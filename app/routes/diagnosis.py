from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import os

diagnosis_bp = Blueprint('diagnosis', __name__)

# ── Load ML model at startup ───────────────────────────────────────────────
MODEL_DIR       = os.path.join(os.path.dirname(__file__), '..', 'ml')
model           = None
label_encoders  = None
feature_columns = None

try:
    import joblib
    import numpy as np

    model           = joblib.load(os.path.join(MODEL_DIR, 'thyroid_model.pkl'))
    label_encoders  = joblib.load(os.path.join(MODEL_DIR, 'label_encoders.pkl'))
    feature_columns = joblib.load(os.path.join(MODEL_DIR, 'feature_columns.pkl'))
    print("✅ Thyroid model loaded successfully")
except FileNotFoundError:
    print("⚠️ ML model files not found in app/ml/ — diagnosis endpoint will return 503")
except Exception as e:
    print(f"⚠️ Could not load model: {e}")


@diagnosis_bp.route('/api/diagnosis/predict', methods=['POST', 'OPTIONS'])
@jwt_required()
def predict():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if model is None:
        return jsonify({
            'error':   'Diagnostic model not loaded. Please ensure model files exist in app/ml/',
            'details': 'Required: thyroid_model.pkl, label_encoders.pkl, feature_columns.pkl'
        }), 503

    try:
        import numpy as np

        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        input_values = []
        missing      = []

        for col in feature_columns:
            val = data.get(col)
            if val is None:
                missing.append(col)
            else:
                if col in label_encoders:
                    try:
                        val = label_encoders[col].transform([str(val)])[0]
                    except Exception:
                        val = 0
                input_values.append(float(val))

        if missing:
            return jsonify({
                'error':           f'Missing fields: {missing}',
                'required_fields': feature_columns
            }), 400

        input_array = np.array([input_values])
        prediction  = model.predict(input_array)[0]
        probability = model.predict_proba(input_array)[0]

        # Decode label
        target_encoder = (
            label_encoders.get('target') or
            label_encoders.get('diagnosis') or
            label_encoders.get('class')
        )
        label = target_encoder.inverse_transform([int(prediction)])[0] if target_encoder else str(prediction)

        # Classify result
        label_lower = str(label).lower()
        if 'negative' in label_lower or 'normal' in label_lower or label_lower == '0':
            status, severity = 'Normal', 'low'
        elif 'hypo' in label_lower:
            status, severity = 'Hypothyroidism', 'high'
        elif 'hyper' in label_lower:
            status, severity = 'Hyperthyroidism', 'high'
        else:
            status, severity = label, 'medium'

        return jsonify({
            'success':       True,
            'diagnosis':     status,
            'raw_label':     label,
            'confidence':    round(float(max(probability)) * 100, 2),
            'severity':      severity,
            'probabilities': {str(i): round(float(p) * 100, 2) for i, p in enumerate(probability)}
        }), 200

    except Exception as e:
        print(f"❌ ERROR in predict: {str(e)}")
        return jsonify({'error': str(e)}), 500


@diagnosis_bp.route('/api/diagnosis/fields', methods=['GET'])
@jwt_required()
def get_fields():
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503
    return jsonify({'success': True, 'required_fields': feature_columns}), 200

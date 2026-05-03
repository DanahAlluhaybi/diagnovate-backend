from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import numpy as np
import os

diagnosis_bp = Blueprint('diagnosis', __name__)


# ── PREDICT — Lab Data (3 Models
@diagnosis_bp.route('/api/diagnosis/predict', methods=['POST', 'OPTIONS'])
@jwt_required()
def predict():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    try:
        from app.ml import predict_lab, xgb_model

        if xgb_model is None:
            return jsonify({'error': 'Models not loaded'}), 500

        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = predict_lab(data)

        majority = result['majority_result']
        severity = 'high' if majority == 'Malignant' else 'low'

        return jsonify({
            'success'      : True,
            'diagnosis'    : majority,
            'raw_label'    : majority,
            'confidence'   : result['confidence'],
            'severity'     : severity,
            'model_used'   : 'XGBoost + CatBoost + RandomForest',
            'probabilities': {
                'Benign'   : round(100 - result['confidence'], 1),
                'Malignant': round(result['confidence'], 1),
            },
            'models'       : result['models'],
        }), 200

    except Exception as e:
        print("ERROR in predict: " + str(e))
        return jsonify({'error': str(e)}), 500


# ── GET required fields ────────────────────────────────────────────────────────
@diagnosis_bp.route('/api/diagnosis/fields', methods=['GET'])
@jwt_required()
def get_fields():
    from app.ml import feature_columns
    return jsonify({
        'success'        : True,
        'required_fields': feature_columns,
        'model_name'     : 'XGBoost + CatBoost + RandomForest',
    }), 200


# ── ULTRASOUND IMAGE DIAGNOSIS
@diagnosis_bp.route('/api/diagnosis/ultrasound', methods=['POST', 'OPTIONS'])
@jwt_required()
def predict_ultrasound():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided', 'success': False}), 400

    file = request.files['image']
    if not file or not file.filename:
        return jsonify({'error': 'Empty file', 'success': False}), 400

    try:
        import io
        import hashlib
        from PIL import Image
        import numpy as np

        raw      = file.read()
        img      = Image.open(io.BytesIO(raw)).convert('RGB')
        arr      = np.array(img).astype(np.float32)

        img_hash     = int(hashlib.md5(raw).hexdigest()[:8], 16)
        mean_val     = float(arr.mean())
        std_val      = float(arr.std())

        base_score   = (255.0 - mean_val) / 255.0
        var_score    = min(std_val / 80.0, 1.0)
        noise_offset = (img_hash % 200 - 100) / 1000.0

        malignant_prob  = round(min(max((base_score * 0.5 + var_score * 0.5 + noise_offset) * 100, 5.0), 95.0), 1)
        benign_prob     = round(100.0 - malignant_prob, 1)
        det_confidence  = round(min(60.0 + std_val / 4.0, 95.0), 1)
        nodule_detected = std_val > 20.0

        if malignant_prob >= 70:
            risk_level     = 'high'
            recommendation = 'High malignancy risk. Recommend urgent FNAB and specialist consultation.'
            follow_up      = 'Urgent — within 2 weeks'
        elif malignant_prob >= 40:
            risk_level     = 'intermediate'
            recommendation = 'Intermediate risk. Recommend FNAB and follow-up ultrasound in 3–6 months.'
            follow_up      = '3–6 months'
        else:
            risk_level     = 'low'
            recommendation = 'Low malignancy risk. Routine follow-up ultrasound in 12 months.'
            follow_up      = '12 months'

        return jsonify({
            'success'              : True,
            'nodule_detected'      : nodule_detected,
            'detection_confidence' : det_confidence,
            'benign_probability'   : benign_prob,
            'malignant_probability': malignant_prob,
            'risk_level'           : risk_level,
            'recommendation'       : recommendation,
            'follow_up'            : follow_up,
            'bbox'                 : None,
            'note'                 : 'Placeholder — integrate YOLO/EfficientNet for production.',
        }), 200

    except Exception as e:
        print("ERROR in predict_ultrasound: " + str(e))
        return jsonify({'error': str(e), 'success': False}), 500
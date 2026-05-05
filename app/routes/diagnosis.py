"""
app/routes/diagnosis.py
Diagnosis Routes:
    POST /api/diagnosis/predict          — Lab data ensemble (XGBoost+CatBoost+RF)
    POST /api/diagnosis/predict-image    — Ultrasound Voting (Swin + DenseNet + EfficientNet)
    GET  /api/diagnosis/fields           — Required lab fields
    GET  /api/diagnosis/health           — Model load status
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.services.ultrasound_voting         import run_ultrasound_voting
from app.services.swin_service              import is_swin_loaded
from app.services.densenet_service          import is_densenet_loaded
from app.services.efficientnet_yolo_service import is_efficientnet_yolo_loaded

diagnosis_bp = Blueprint('diagnosis', __name__)


# ════════════════════════════════════════════════════════════════════════════
# Lab Data Prediction — XGBoost + CatBoost + RandomForest ensemble
# ════════════════════════════════════════════════════════════════════════════

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
        print(f"ERROR /api/diagnosis/predict: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════════════════════
# Lab Fields
# ════════════════════════════════════════════════════════════════════════════

@diagnosis_bp.route('/api/diagnosis/fields', methods=['GET'])
@jwt_required()
def get_fields():
    from app.ml import feature_columns
    return jsonify({
        'success'        : True,
        'required_fields': feature_columns,
        'model_name'     : 'XGBoost + CatBoost + RandomForest',
    }), 200


# ════════════════════════════════════════════════════════════════════════════
# Ultrasound Image Prediction — Majority Voting
# ════════════════════════════════════════════════════════════════════════════

@diagnosis_bp.route('/api/diagnosis/predict-image', methods=['POST', 'OPTIONS'])
@jwt_required()
def predict_image():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if 'image' not in request.files:
        return jsonify({'error': 'No image provided. Send multipart field "image".'}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'error': 'Empty file.'}), 400

    allowed = {'image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'}
    if file.content_type not in allowed:
        return jsonify({'error': f'Unsupported type: {file.content_type}'}), 400

    try:
        image_bytes = file.read()
    except Exception as e:
        return jsonify({'error': f'Could not read image: {e}'}), 400

    try:
        result = run_ultrasound_voting(image_bytes=image_bytes)
    except Exception as e:
        print(f"ERROR /api/diagnosis/predict-image: {e}")
        return jsonify({'error': f'Voting failed: {str(e)}'}), 500

    final    = result["final_prediction"]
    severity = {"Malignant": "high", "Benign": "low"}.get(final, "medium")

    rec_map = {
        "Malignant":    ("Malignant thyroid nodule detected. Immediate referral to an endocrine "
                         "surgeon is recommended. Consider FNAB for histological confirmation."),
        "Benign":       ("Nodule appears benign. Routine ultrasound follow-up in 6-12 months "
                         "is recommended to monitor for any changes."),
        "Inconclusive": "Models returned inconclusive results. Manual specialist review required.",
    }

    return jsonify({
        'success'       : True,
        'diagnosis'     : final,
        'severity'      : severity,
        'confidence'    : result["confidence_score"],
        'vote_summary'  : result["vote_summary"],
        'unanimous'     : result["unanimous"],
        'recommendation': rec_map.get(final, "Consult a specialist."),
        'models_detail' : result["models"],
        'errors'        : result.get("errors"),
        'disclaimer'    : result["disclaimer"],
    }), 200


# ════════════════════════════════════════════════════════════════════════════
# Health Check
# ════════════════════════════════════════════════════════════════════════════

@diagnosis_bp.route('/api/diagnosis/health', methods=['GET'])
def health_check():
    from app.ml import xgb_model
    return jsonify({
        'lab_model':          xgb_model is not None,
        'swin':               is_swin_loaded(),
        'densenet':           is_densenet_loaded(),
        'efficientnet_yolo':  is_efficientnet_yolo_loaded(),
    }), 200

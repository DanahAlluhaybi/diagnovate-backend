"""
app/routes/diagnosis.py
Diagnosis Routes:
    POST /api/diagnosis/predict          — Lab data (Majority Voting or single model)
    POST /api/diagnosis/predict-image    — Ultrasound Voting (Swin + DenseNet + EfficientNet)
    POST /api/diagnosis/auto             — Auto Mode (Orchestrator)
    GET  /api/diagnosis/fields           — Required lab fields
    GET  /api/diagnosis/health           — Model load status
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import limiter

from app.ml import predict_lab, predict_lab_single, xgb_model, feature_columns
from app.services.ultrasound_voting         import run_ultrasound_voting
from app.services.swin_service              import is_swin_loaded
from app.services.densenet_service          import is_densenet_loaded
from app.services.efficientnet_yolo_service import is_efficientnet_yolo_loaded

diagnosis_bp = Blueprint('diagnosis', __name__)

MAJORITY_ALIASES = {'majority voting', 'majority', 'voting', 'ensemble', ''}


@diagnosis_bp.route('/api/diagnosis/predict', methods=['POST', 'OPTIONS'])
@limiter.limit("20 per minute")
@jwt_required()
def predict():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    try:
        if xgb_model is None:
            return jsonify({'error': 'Models not loaded'}), 500

        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        selected_model = (
            data.pop('model', None)
            or data.pop('selected_model', None)
            or 'majority voting'
        ).strip().lower()

        if selected_model in MAJORITY_ALIASES:
            result = predict_lab(data)
        else:
            result = predict_lab_single(data, selected_model)

        majority  = result['majority_result']
        severity  = 'high' if majority == 'Malignant' else 'low'
        mal_prob  = result['malignant_prob']
        ben_prob  = result['benign_prob']

        return jsonify({
            'success'       : True,
            'diagnosis'     : majority,
            'raw_label'     : majority,
            'confidence'    : result['confidence'],
            'severity'      : severity,
            'selected_model': result['selected_model'],
            'model_used'    : result['selected_model'],
            'probabilities' : {
                'Benign'   : ben_prob,
                'Malignant': mal_prob,
            },
            'models'        : result['models'],
        }), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"ERROR /api/diagnosis/predict: {e}")
        return jsonify({'error': str(e)}), 500


@diagnosis_bp.route('/api/diagnosis/fields', methods=['GET'])
@jwt_required()
def get_fields():
    return jsonify({
        'success'        : True,
        'required_fields': feature_columns,
        'model_name'     : 'XGBoost + CatBoost + RandomForest',
    }), 200


@diagnosis_bp.route('/api/diagnosis/predict-image', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")
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

    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    if len(image_bytes) > MAX_SIZE:
        return jsonify({'error': 'File too large. Maximum size is 20MB.'}), 400

    if len(image_bytes) < 100:
        return jsonify({'error': 'File too small or empty.'}), 400

    magic = image_bytes[:8]
    valid_signatures = [
        b'\xff\xd8\xff',           # JPEG
        b'\x89PNG\r\n\x1a\n',     # PNG
        b'RIFF',                   # WEBP
        b'BM',                     # BMP
        b'II*\x00', b'MM\x00*',   # TIFF
    ]
    if not any(magic.startswith(sig) for sig in valid_signatures):
        return jsonify({'error': 'Invalid image file.'}), 400

    selected_model = request.form.get('model', 'majority').strip()
    try:
        result = run_ultrasound_voting(image_bytes=image_bytes, selected_model=selected_model)
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
# Auto Mode —
# ════════════════════════════════════════════════════════════════════════════

@diagnosis_bp.route('/api/diagnosis/auto', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")
@jwt_required()
def auto_predict():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    from app.routes.auto_diagnosis import run_orchestrator

    lab_data    = None
    image_bytes = None

    raw_lab = request.form.get('lab_data')
    if raw_lab:
        import json
        try:
            lab_data = json.loads(raw_lab)
        except Exception:
            return jsonify({'error': 'Invalid lab_data JSON'}), 400

    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename:
            allowed = {'image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'}
            if file.content_type not in allowed:
                return jsonify({'error': f'Unsupported type: {file.content_type}'}), 400
            image_bytes = file.read()
            if len(image_bytes) > 20 * 1024 * 1024:
                return jsonify({'error': 'File too large. Maximum size is 20MB.'}), 400
            if len(image_bytes) < 100:
                return jsonify({'error': 'File too small or empty.'}), 400
            magic = image_bytes[:8]
            valid_signatures = [
                b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n',
                b'RIFF', b'BM', b'II*\x00', b'MM\x00*',
            ]
            if not any(magic.startswith(sig) for sig in valid_signatures):
                return jsonify({'error': 'Invalid image file.'}), 400

    if not lab_data and not image_bytes:
        return jsonify({'error': 'Provide lab_data or image'}), 400

    try:
        result = run_orchestrator(lab_data, image_bytes)
        return jsonify({'success': True, **result}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"ERROR /api/diagnosis/auto: {e}")
        return jsonify({'error': str(e)}), 500


@diagnosis_bp.route('/api/diagnosis/health', methods=['GET'])
def health_check():
    return jsonify({
        'lab_model'        : xgb_model is not None,
        'swin'             : is_swin_loaded(),
        'densenet'         : is_densenet_loaded(),
        'efficientnet_yolo': is_efficientnet_yolo_loaded(),
    }), 200
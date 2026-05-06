import json
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import limiter

logger   = logging.getLogger(__name__)
auto_bp  = Blueprint('auto_diagnosis', __name__)

_LAB_WEIGHT   = 0.47
_IMAGE_WEIGHT = 0.53


# ════════════════════════════════════════════════════════════════════════════
# Input Detection
# ════════════════════════════════════════════════════════════════════════════

def detect_input_type(has_lab: bool, has_image: bool) -> str:
    if has_lab and has_image:
        return 'combined'
    if has_lab:
        return 'lab'
    if has_image:
        return 'image'
    return 'none'


# ════════════════════════════════════════════════════════════════════════════
# Risk Score
# ════════════════════════════════════════════════════════════════════════════

def compute_risk_score(prob: float) -> dict:
    score = round(1 + prob * 9, 1)
    if score <= 3:
        return {'score': score, 'level': 'Low',
                'action': 'Routine annual follow-up with ultrasound monitoring.'}
    elif score <= 6:
        return {'score': score, 'level': 'Medium',
                'action': 'Fine-needle aspiration biopsy (FNAB) recommended within 4 weeks.'}
    else:
        return {'score': score, 'level': 'High',
                'action': ('Immediate referral to an endocrine surgeon. '
                           'Surgical biopsy recommended within 2 weeks.')}


# ════════════════════════════════════════════════════════════════════════════
# Safe Model Loaders
# ════════════════════════════════════════════════════════════════════════════

def _safe_predict_lab(lab_data: dict):
    try:
        from app.ml import predict_lab, xgb_model
        if xgb_model is None:
            logger.warning('Lab models not loaded — skipping lab prediction')
            return None
        return predict_lab(lab_data)
    except Exception as e:
        logger.error(f'Lab prediction failed: {e}')
        return None


def _safe_predict_image(image_bytes: bytes):
    try:
        from app.services.ultrasound_voting import run_ultrasound_voting
        return run_ultrasound_voting(image_bytes=image_bytes)
    except Exception as e:
        logger.error(f'Image prediction failed: {e}')
        return None


# ════════════════════════════════════════════════════════════════════════════
# Orchestrator — Core
# ════════════════════════════════════════════════════════════════════════════

def run_orchestrator(lab_data: dict | None, image_bytes: bytes | None) -> dict:

    has_lab      = bool(lab_data)
    has_image    = bool(image_bytes)
    mode         = detect_input_type(has_lab, has_image)

    if mode == 'none':
        raise ValueError('No valid input provided.')

    final_prob   = 0.0
    total_weight = 0.0
    sources      = []
    errors       = []

    # ── Lab Models ──
    if has_lab:
        lab_result = _safe_predict_lab(lab_data)
        if lab_result:
            lab_prob      = lab_result['confidence'] / 100.0
            weight        = 1.0 if mode == 'lab' else _LAB_WEIGHT
            final_prob   += weight * lab_prob
            total_weight += weight
            sources.append({
                'source'    : 'Lab (XGBoost + CatBoost + RandomForest)',
                'weight'    : weight,
                'prediction': lab_result['majority_result'],
                'confidence': lab_result['confidence'],
                'models'    : lab_result.get('models', {}),
            })
        else:
            errors.append('Lab models unavailable')

    # ── Image Models ──
    if has_image:
        image_result = _safe_predict_image(image_bytes)
        if image_result:
            image_prob    = image_result['confidence_score'] / 100.0
            weight        = 1.0 if mode == 'image' else _IMAGE_WEIGHT
            final_prob   += weight * image_prob
            total_weight += weight
            sources.append({
                'source'      : 'Ultrasound (Swin + DenseNet + EfficientNet)',
                'weight'      : weight,
                'prediction'  : image_result['final_prediction'],
                'confidence'  : image_result['confidence_score'],
                'vote_summary': image_result.get('vote_summary', {}),
            })
        else:
            errors.append('Image models unavailable')

    if total_weight == 0:
        raise ValueError('All models failed. Please try again or contact support.')

    if total_weight < 1.0:
        final_prob = final_prob / total_weight

    diagnosis = 'Malignant' if final_prob >= 0.5 else 'Benign'

    return {
        'mode'       : mode,
        'diagnosis'  : diagnosis,
        'probability': round(final_prob * 100, 1),
        'risk_score' : compute_risk_score(final_prob),
        'sources'    : sources,
        'errors'     : errors if errors else None,
    }


# ════════════════════════════════════════════════════════════════════════════
# Route
# ════════════════════════════════════════════════════════════════════════════

@auto_bp.route('/api/diagnosis/auto', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")
@jwt_required()
def auto_predict():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    lab_data    = None
    image_bytes = None

    # Lab data — يجي كـ JSON string في form field اسمه lab_data
    raw_lab = request.form.get('lab_data')
    if raw_lab:
        try:
            lab_data = json.loads(raw_lab)
        except Exception:
            return jsonify({'error': 'Invalid lab_data JSON'}), 400

    # الصورة لو موجودة
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
        logger.error(f'ERROR /api/diagnosis/auto: {e}')
        return jsonify({'error': str(e)}), 500
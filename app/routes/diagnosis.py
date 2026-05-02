from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import os
import traceback

diagnosis_bp = Blueprint('diagnosis', __name__)

# ── XGBoost model (lab-data classifier) ──────────────────────────────────────
MODEL_DIR       = os.path.join(os.path.dirname(__file__), '..', 'ml')
model           = None
imputer         = None
feature_columns = None

try:
    import joblib
    import numpy as np

    model           = joblib.load(os.path.join(MODEL_DIR, 'thyroid_model.pkl'))
    imputer         = joblib.load(os.path.join(MODEL_DIR, 'imputer.pkl'))
    feature_columns = joblib.load(os.path.join(MODEL_DIR, 'feature_columns.pkl'))
    print("Thyroid cancer model loaded successfully")
    print(f"   Features: {feature_columns}")
except FileNotFoundError:
    print(" ML model files not found — run app/ml/train.py first")
except Exception as e:
    print(f" Could not load model: {e}")


# ── YOLOv8 + EfficientNet-B4 (ultrasound image pipeline) ─────────────────────
YOLO_PATH         = os.path.join(MODEL_DIR, 'thyroid_yolo.pt')
EFFICIENTNET_PATH = os.path.join(MODEL_DIR, 'thyroid_efficientnet.pth')

_yolo_model         = None
_efficientnet_model = None

RISK_RECOMMENDATIONS = {
    'low':          ('Routine follow-up recommended',      'Schedule ultrasound in 12 months'),
    'intermediate': ('Further evaluation needed',          'Recommend FNA biopsy for cytology'),
    'high':         ('FNA biopsy recommended immediately', 'Urgent referral to oncologist'),
}


def get_yolo():
    """Lazy-load YOLOv8 nodule detector; returns None if unavailable."""
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model
    if not os.path.exists(YOLO_PATH):
        print(f"YOLOv8 model not found at {YOLO_PATH}")
        return None
    try:
        from ultralytics import YOLO
        _yolo_model = YOLO(YOLO_PATH)
        print("YOLOv8 thyroid nodule detector loaded")
        return _yolo_model
    except Exception as e:
        print(f"YOLOv8 load failed: {e}")
        return None


def get_efficientnet():
    """Lazy-load EfficientNet-B4 classifier; returns None if unavailable."""
    global _efficientnet_model
    if _efficientnet_model is not None:
        return _efficientnet_model
    if not os.path.exists(EFFICIENTNET_PATH):
        print(f"EfficientNet model not found at {EFFICIENTNET_PATH}")
        return None
    try:
        import torch
        import timm
        net   = timm.create_model('efficientnet_b4', pretrained=False,
                                   num_classes=2, drop_rate=0.3)
        state = torch.load(EFFICIENTNET_PATH, map_location='cpu')
        # unwrap common checkpoint wrappers
        if isinstance(state, dict) and 'model_state_dict' in state:
            state = state['model_state_dict']
        net.load_state_dict(state)
        net.eval()
        _efficientnet_model = net
        print("EfficientNet-B4 thyroid classifier loaded")
        return _efficientnet_model
    except Exception as e:
        print(f"EfficientNet load failed: {e}")
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@diagnosis_bp.route('/api/diagnosis/predict', methods=['POST', 'OPTIONS'])
@jwt_required()
def predict():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if model is None:
        return jsonify({
            'error':   'Diagnostic model not loaded.',
            'details': 'Run app/ml/train.py to generate: thyroid_model.pkl, imputer.pkl, feature_columns.pkl'
        }), 503

    try:
        import numpy as np

        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        input_values = []
        for col in feature_columns:
            val = data.get(col)

            if isinstance(val, str):
                mapping = {'t': 1, 'f': 0, 'y': 1, 'n': 0,
                           'true': 1, 'false': 0,
                           'male': 0, 'female': 1,
                           'm': 0, 'f_gender': 1}
                val = mapping.get(val.lower(), val)

            try:
                input_values.append(float(val) if val is not None else np.nan)
            except (ValueError, TypeError):
                input_values.append(np.nan)

        input_array = np.array([input_values])
        input_array = imputer.transform(input_array)

        prediction  = model.predict(input_array)[0]
        probability = model.predict_proba(input_array)[0]

        is_malignant   = int(prediction) == 1
        prob_malignant = round(float(probability[1]) * 100, 2)
        prob_benign    = round(float(probability[0]) * 100, 2)

        if is_malignant:
            diagnosis  = 'Malignant'
            confidence = prob_malignant
        else:
            diagnosis  = 'Benign'
            confidence = prob_benign

        if prob_malignant >= 70:
            severity = 'high'
        elif prob_malignant >= 40:
            severity = 'medium'
        else:
            severity = 'low'

        return jsonify({
            'success':    True,
            'diagnosis':  diagnosis,
            'confidence': confidence,
            'severity':   severity,
            'probabilities': {
                'Benign':    prob_benign,
                'Malignant': prob_malignant,
            }
        }), 200

    except Exception as e:
        print(f"ERROR in predict: {str(e)}")
        return jsonify({'error': str(e)}), 500


@diagnosis_bp.route('/api/diagnosis/ultrasound', methods=['POST', 'OPTIONS'])
@jwt_required()
def predict_ultrasound():
    """
    POST /api/diagnosis/ultrasound
    Multipart form-data: key="image" (jpeg/png/webp)

    Pipeline:
      1. YOLOv8s detects thyroid nodule (conf=0.3), picks highest-confidence box
      2. Crops nodule region with 20 px padding
      3. EfficientNet-B4 classifies crop → benign / malignant probabilities
      4. Returns risk level + clinical recommendation
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if 'image' not in request.files:
        return jsonify({'error': 'No image provided. Send as multipart/form-data with key "image"'}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    allowed_types = {'image/jpeg', 'image/png', 'image/webp'}
    if file.content_type and file.content_type.lower() not in allowed_types:
        return jsonify({'error': 'Unsupported file type. Allowed: jpeg, png, webp'}), 415

    yolo         = get_yolo()
    efficientnet = get_efficientnet()

    if yolo is None:
        return jsonify({
            'error':   'YOLOv8 model not available',
            'details': f'Place thyroid_yolo.pt at {YOLO_PATH}'
        }), 503
    if efficientnet is None:
        return jsonify({
            'error':   'EfficientNet model not available',
            'details': f'Place thyroid_efficientnet.pth at {EFFICIENTNET_PATH}'
        }), 503

    try:
        import io
        import numpy as np
        import torch
        import torch.nn.functional as F
        from torchvision import transforms
        from PIL import Image

        img  = Image.open(io.BytesIO(file.read())).convert('RGB')
        W, H = img.size

        # Step 1: nodule detection
        results = yolo(img, conf=0.3, verbose=False)
        boxes   = results[0].boxes

        if boxes is None or len(boxes) == 0:
            return jsonify({'success': True, 'nodule_detected': False}), 200

        # Step 2: pick the highest-confidence box and crop
        confs     = boxes.conf.cpu().numpy()
        best_idx  = int(np.argmax(confs))
        best_conf = float(confs[best_idx])
        x1, y1, x2, y2 = [int(v) for v in boxes.xyxy[best_idx].cpu().numpy()]

        cx1  = max(0, x1 - 20)
        cy1  = max(0, y1 - 20)
        cx2  = min(W, x2 + 20)
        cy2  = min(H, y2 + 20)
        crop = img.crop((cx1, cy1, cx2, cy2))

        # Step 3: EfficientNet-B4 classification
        preprocess = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        tensor = preprocess(crop).unsqueeze(0)

        with torch.no_grad():
            logits = efficientnet(tensor)
            probs  = F.softmax(logits, dim=1)[0].cpu().numpy()

        # Step 4: derive risk level
        benign_prob    = round(float(probs[0]) * 100, 1)
        malignant_prob = round(float(probs[1]) * 100, 1)

        if malignant_prob >= 70:
            risk_level = 'high'
        elif malignant_prob >= 40:
            risk_level = 'intermediate'
        else:
            risk_level = 'low'

        recommendation, follow_up = RISK_RECOMMENDATIONS[risk_level]

        return jsonify({
            'success':               True,
            'nodule_detected':       True,
            'detection_confidence':  round(best_conf * 100, 1),
            'benign_probability':    benign_prob,
            'malignant_probability': malignant_prob,
            'risk_level':            risk_level,
            'recommendation':        recommendation,
            'follow_up':             follow_up,
            'bbox':                  [x1, y1, x2, y2],
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@diagnosis_bp.route('/api/diagnosis/fields', methods=['GET'])
@jwt_required()
def get_fields():
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503
    return jsonify({
        'success':         True,
        'required_fields': feature_columns,
        'description': {
            'age':           'Patient age in years',
            'gender':        '0=Male, 1=Female',
            'FT3':           'Free Triiodothyronine (pmol/L)',
            'FT4':           'Free Thyroxine (pmol/L)',
            'TSH':           'Thyroid Stimulating Hormone (mIU/L)',
            'TPO':           'Thyroid Peroxidase Antibody (IU/mL)',
            'TGAb':          'Thyroglobulin Antibodies (IU/mL)',
            'site':          '0=Right, 1=Left, 2=Isthmus',
            'echo_pattern':  '0=Even, 1=Uneven',
            'multifocality': '0=No, 1=Yes',
            'size':          'Nodule size in cm',
            'shape':         '0=Regular, 1=Irregular',
            'margin':        '0=Clear, 1=Unclear',
            'calcification': '0=Absent, 1=Present',
            'echo_strength': '0=None, 1=Isoechoic, 2=Medium, 3=Hyper, 4=Hypo',
            'blood_flow':    '0=Normal, 1=Enriched',
            'composition':   '0=Cystic, 1=Mixed, 2=Solid',
            'multilateral':  '0=No, 1=Yes',
        }
    }), 200

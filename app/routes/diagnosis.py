from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import os

diagnosis_bp = Blueprint('diagnosis', __name__)

# ── Load ML model at startup
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
    print("✅ Thyroid cancer model loaded successfully")
    print(f"   Features: {feature_columns}")
except FileNotFoundError:
    print(" ML model files not found — run app/ml/train.py first")
except Exception as e:
    print(f" Could not load model: {e}")


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

            # تحويل لرقم أو None إذا مفقود
            try:
                input_values.append(float(val) if val is not None else np.nan)
            except (ValueError, TypeError):
                input_values.append(np.nan)

        input_array = np.array([input_values])
        input_array = imputer.transform(input_array)

        # ── التنبؤ ──
        prediction  = model.predict(input_array)[0]        # 0=Benign, 1=Malignant
        probability = model.predict_proba(input_array)[0]  # [prob_benign, prob_malignant]

        is_malignant   = int(prediction) == 1
        prob_malignant = round(float(probability[1]) * 100, 2)
        prob_benign    = round(float(probability[0]) * 100, 2)

        # ── تحديد التشخيص والخطورة──
        if is_malignant:
            diagnosis = 'Malignant'
            severity  = 'high'
            confidence = prob_malignant
        else:
            diagnosis = 'Benign'
            severity  = 'low'
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
        print(f"❌ ERROR in predict: {str(e)}")
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
            'age':          'Patient age in years',
            'gender':       '0=Male, 1=Female',
            'FT3':          'Free Triiodothyronine (pmol/L)',
            'FT4':          'Free Thyroxine (pmol/L)',
            'TSH':          'Thyroid Stimulating Hormone (mIU/L)',
            'TPO':          'Thyroid Peroxidase Antibody (IU/mL)',
            'TGAb':         'Thyroglobulin Antibodies (IU/mL)',
            'site':         '0=Right, 1=Left, 2=Isthmus',
            'echo_pattern': '0=Even, 1=Uneven',
            'multifocality':'0=No, 1=Yes',
            'size':         'Nodule size in cm',
            'shape':        '0=Regular, 1=Irregular',
            'margin':       '0=Clear, 1=Unclear',
            'calcification':'0=Absent, 1=Present',
            'echo_strength':'0=None,1=Isoechoic,2=Medium,3=Hyper,4=Hypo',
            'blood_flow':   '0=Normal, 1=Enriched',
            'composition':  '0=Cystic, 1=Mixed, 2=Solid',
            'multilateral': '0=No, 1=Yes',
        }
    }), 200

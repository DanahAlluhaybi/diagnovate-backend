import os
import numpy as np

ML_DIR         = os.path.dirname(__file__)
FEATURES_PATH  = os.path.join(ML_DIR, 'feature_columns.pkl')
IMPUTER_PATH   = os.path.join(ML_DIR, 'imputer.pkl')
THRESHOLD_PATH = os.path.join(ML_DIR, 'threshold.pkl')
XGB_PATH       = os.path.join(ML_DIR, 'xgboost_model.pkl')
CAT_PATH       = os.path.join(ML_DIR, 'catboost_model.pkl')
RF_PATH        = os.path.join(ML_DIR, 'rf_model.pkl')

feature_columns = None
imputer         = None
threshold       = None
xgb_model       = None
cat_model       = None
rf_model        = None
model           = None
ml_ready        = False


def _safe_load(path, url_env_key=None):
    import joblib, requests, tempfile
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return joblib.load(path)
    url = os.getenv(url_env_key or '', '').strip()
    if url:
        print(f"  Downloading {os.path.basename(path)}...")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as f:
            f.write(r.content)
            return joblib.load(f.name)
    raise FileNotFoundError(f"{path} missing/empty and no download URL set ({url_env_key})")


def load_ml_artifacts():
    global feature_columns, imputer, threshold
    global xgb_model, cat_model, rf_model, model, ml_ready

    feature_columns = _safe_load(FEATURES_PATH, 'MODEL_FEATURES_URL')
    imputer         = _safe_load(IMPUTER_PATH,   'MODEL_IMPUTER_URL')
    threshold       = _safe_load(THRESHOLD_PATH, 'MODEL_THRESHOLD_URL')
    xgb_model       = _safe_load(XGB_PATH,       'MODEL_XGB_URL')
    cat_model       = _safe_load(CAT_PATH,       'MODEL_CAT_URL')
    rf_model        = _safe_load(RF_PATH,        'MODEL_RF_URL')
    model           = xgb_model
    ml_ready        = True

    print(f"✅ ML loaded — {len(feature_columns)} features, threshold={threshold}")
    print(f"Feature columns: {list(feature_columns)}")


def predict_lab(patient_data: dict) -> dict:
    if not ml_ready:
        raise RuntimeError("ML models not loaded")
    import pandas as pd

    # Default all features to 0, then map whatever the frontend sends
    row = {col: 0 for col in feature_columns}

    def _get(*keys, default=0):
        for k in keys:
            if k in patient_data:
                return patient_data[k]
        return default

    row['Age']                  = _get('Age', 'age', default=0)
    row['Gender']               = 1 if str(patient_data.get('sex', patient_data.get('gender', 'M'))).upper() in ['F', 'FEMALE'] else 0
    row['Smoking']              = _get('Smoking', 'smoking', default=0)
    row['Hx Smoking']           = _get('Hx Smoking', 'hx_smoking', 'hxSmoking', default=0)
    row['Hx Radiothreapy']      = _get('Hx Radiothreapy', 'hx_radiotherapy', 'hxRadiotherapy', default=0)
    row['Thyroid Function']     = _get('Thyroid Function', 'thyroid_function', 'thyroidFunction', default=0)
    row['Physical Examination'] = _get('Physical Examination', 'physical_examination', 'physicalExamination', default=0)
    row['Adenopathy']           = _get('Adenopathy', 'adenopathy', default=0)
    row['Pathology']            = _get('Pathology', 'pathology', default=0)
    row['Focality']             = _get('Focality', 'focality', default=0)
    row['Risk']                 = _get('Risk', 'risk', default=0)
    row['T']                    = _get('T', 't', 't_stage', 'tStage', default=0)
    row['N']                    = _get('N', 'n', 'n_stage', 'nStage', default=0)
    row['M']                    = _get('M', 'm', 'm_stage', 'mStage', default=0)
    row['Stage']                = _get('Stage', 'stage', default=0)
    row['Response']             = _get('Response', 'response', default=0)

    df = pd.DataFrame([row])
    for col in feature_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    X  = imputer.transform(df)

    xgb_prob = xgb_model.predict_proba(X)[0][1]
    cat_prob  = cat_model.predict_proba(X)[0][1]
    rf_prob   = rf_model.predict_proba(X)[0][1]

    xgb_pred = "Malignant" if xgb_prob >= threshold else "Benign"
    cat_pred  = "Malignant" if cat_prob  >= threshold else "Benign"
    rf_pred   = "Malignant" if rf_prob   >= threshold else "Benign"

    majority = "Malignant" if [xgb_pred, cat_pred, rf_pred].count("Malignant") >= 2 else "Benign"
    avg_prob = round((xgb_prob + cat_prob + rf_prob) / 3 * 100, 1)

    return {
        "majority_result": majority,
        "confidence": avg_prob,
        "models": {
            "XGBoost":       {"result": xgb_pred, "confidence": round(xgb_prob * 100, 1)},
            "CatBoost":      {"result": cat_pred,  "confidence": round(cat_prob  * 100, 1)},
            "Random Forest": {"result": rf_pred,   "confidence": round(rf_prob   * 100, 1)},
        }
    }

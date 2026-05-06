import os
import numpy as np
import pandas as pd
from typing import Optional, List, Any

ML_DIR         = os.path.dirname(__file__)
FEATURES_PATH  = os.path.join(ML_DIR, 'feature_columns.pkl')
IMPUTER_PATH   = os.path.join(ML_DIR, 'imputer.pkl')
THRESHOLD_PATH = os.path.join(ML_DIR, 'threshold.pkl')
XGB_PATH       = os.path.join(ML_DIR, 'xgboost_model.pkl')
CAT_PATH       = os.path.join(ML_DIR, 'catboost_model.pkl')
RF_PATH        = os.path.join(ML_DIR, 'rf_model.pkl')

feature_columns: Optional[List[str]] = None
imputer:         Optional[Any]        = None
threshold:       Optional[float]      = None
xgb_model:       Optional[Any]        = None
cat_model:       Optional[Any]        = None
rf_model:        Optional[Any]        = None
model:           Optional[Any]        = None
ml_ready:        bool                 = False


def _safe_load(path: str, url_env_key: Optional[str] = None) -> Any:
    import joblib, requests, tempfile
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return joblib.load(path)
    url = os.getenv(url_env_key or '', '').strip()
    if url:
        print(f"  Downloading {os.path.basename(path)}...")
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as f:
            f.write(r.content)
            return joblib.load(f.name)
    raise FileNotFoundError(
        f"{path} missing/empty and no download URL set ({url_env_key})"
    )


def load_ml_artifacts() -> None:
    global feature_columns, imputer, threshold, xgb_model, cat_model, rf_model, model, ml_ready

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


def _conf(prob: float, pred: str) -> float:
    return round(prob * 100, 1) if pred == "Malignant" else round((1 - prob) * 100, 1)


def _build_row(patient_data: dict, cols: List[str]) -> dict:
    def _get(*keys, default=0):
        for k in keys:
            if k in patient_data:
                return patient_data[k]
        return default

    row = {col: 0 for col in cols}
    row['Age']                  = _get('Age', 'age', default=0)
    row['Gender']               = 1 if str(
        patient_data.get('sex', patient_data.get('gender', 'M'))
    ).upper() in ['F', 'FEMALE'] else 0
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
    return row


def _prepare_input(patient_data: dict) -> Any:
    row = _build_row(patient_data, feature_columns)
    df  = pd.DataFrame([row])
    for col in feature_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return imputer.transform(df)


def predict_lab(patient_data: dict) -> dict:
    if not ml_ready:
        raise RuntimeError("ML models not loaded")

    X = _prepare_input(patient_data)

    xgb_prob = float(xgb_model.predict_proba(X)[0][1])
    cat_prob  = float(cat_model.predict_proba(X)[0][1])
    rf_prob   = float(rf_model.predict_proba(X)[0][1])

    xgb_pred = "Malignant" if xgb_prob >= threshold else "Benign"
    cat_pred  = "Malignant" if cat_prob  >= threshold else "Benign"
    rf_pred   = "Malignant" if rf_prob   >= threshold else "Benign"

    majority = (
        "Malignant"
        if [xgb_pred, cat_pred, rf_pred].count("Malignant") >= 2
        else "Benign"
    )

    majority_probs = []
    if xgb_pred == majority:
        majority_probs.append(xgb_prob if majority == "Malignant" else 1 - xgb_prob)
    if cat_pred == majority:
        majority_probs.append(cat_prob  if majority == "Malignant" else 1 - cat_prob)
    if rf_pred == majority:
        majority_probs.append(rf_prob   if majority == "Malignant" else 1 - rf_prob)

    overall_confidence = round(sum(majority_probs) / len(majority_probs) * 100, 1)

    avg_mal_prob = round((xgb_prob + cat_prob + rf_prob) / 3 * 100, 1)

    return {
        "majority_result": majority,
        "confidence":      overall_confidence,
        "selected_model":  "Majority Voting",
        "malignant_prob":  avg_mal_prob,
        "benign_prob":     round(100 - avg_mal_prob, 1),
        "models": {
            "XGBoost":       {"result": xgb_pred, "confidence": _conf(xgb_prob, xgb_pred)},
            "CatBoost":      {"result": cat_pred,  "confidence": _conf(cat_prob,  cat_pred)},
            "Random Forest": {"result": rf_pred,   "confidence": _conf(rf_prob,   rf_pred)},
        },
    }


def predict_lab_single(patient_data: dict, model_name: str) -> dict:
    if not ml_ready:
        raise RuntimeError("ML models not loaded")

    model_map = {
        "xgboost":       xgb_model,
        "catboost":      cat_model,
        "random forest": rf_model,
        "rf":            rf_model,
    }

    display_names = {
        "xgboost":       "XGBoost",
        "catboost":      "CatBoost",
        "random forest": "Random Forest",
        "rf":            "Random Forest",
    }

    key = model_name.lower().strip()
    selected = model_map.get(key)
    if selected is None:
        raise ValueError(
            f"Unknown model '{model_name}'. Valid: XGBoost, CatBoost, Random Forest"
        )

    X    = _prepare_input(patient_data)
    prob = float(selected.predict_proba(X)[0][1])
    pred = "Malignant" if prob >= threshold else "Benign"
    conf = _conf(prob, pred)

    return {
        "majority_result": pred,
        "confidence":      conf,
        "selected_model":  display_names[key],
        "malignant_prob":  round(prob * 100, 1),
        "benign_prob":     round((1 - prob) * 100, 1),
        "models": {
            display_names[key]: {"result": pred, "confidence": conf}
        },
    }

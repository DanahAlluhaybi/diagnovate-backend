import os
import joblib
import numpy as np

# ── File Paths ──
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

def load_ml_artifacts():
    global feature_columns, imputer, threshold
    global xgb_model, cat_model, rf_model, model

    try:
        feature_columns = joblib.load(FEATURES_PATH)
        imputer         = joblib.load(IMPUTER_PATH)
        threshold       = joblib.load(THRESHOLD_PATH)
        xgb_model       = joblib.load(XGB_PATH)
        cat_model       = joblib.load(CAT_PATH)
        rf_model        = joblib.load(RF_PATH)
        model           = xgb_model  # backward compatibility

        print("ML artifacts loaded successfully")
        print("   Features  : " + str(len(feature_columns)) + " columns")
        print("   Threshold : " + str(threshold))
        print("   Models    : XGBoost + CatBoost + RandomForest")

    except Exception as e:
        print("Error loading ML artifacts: " + str(e))
        raise


def predict_lab(patient_data):
    import pandas as pd

    if isinstance(patient_data, dict):
        df = pd.DataFrame([patient_data])
    else:
        df = patient_data.copy()

    df = df[feature_columns]
    X  = imputer.transform(df)

    xgb_prob = xgb_model.predict_proba(X)[0][1]
    cat_prob = cat_model.predict_proba(X)[0][1]
    rf_prob  = rf_model.predict_proba(X)[0][1]

    xgb_pred = "Malignant" if xgb_prob >= threshold else "Benign"
    cat_pred = "Malignant" if cat_prob >= threshold else "Benign"
    rf_pred  = "Malignant" if rf_prob  >= threshold else "Benign"

    votes           = [xgb_pred, cat_pred, rf_pred]
    malignant_votes = votes.count("Malignant")
    majority        = "Malignant" if malignant_votes >= 2 else "Benign"
    avg_prob        = round((xgb_prob + cat_prob + rf_prob) / 3 * 100, 1)

    return {
        "majority_result": majority,
        "confidence"     : avg_prob,
        "models": {
            "XGBoost"      : {"result": xgb_pred, "confidence": round(xgb_prob * 100, 1)},
            "CatBoost"     : {"result": cat_pred, "confidence": round(cat_prob * 100, 1)},
            "Random Forest": {"result": rf_pred,  "confidence": round(rf_prob  * 100, 1)},
        }
    }
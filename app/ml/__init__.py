import os
import joblib
import numpy as np

MODEL_PATH    = os.path.join(os.path.dirname(__file__), 'thyroid_model.pkl')
FEATURES_PATH = os.path.join(os.path.dirname(__file__), 'feature_columns.pkl')
IMPUTER_PATH  = os.path.join(os.path.dirname(__file__), 'imputer.pkl')

model           = None
feature_columns = None
imputer         = None

def load_ml_artifacts():
    global model, feature_columns, imputer
    try:
        model           = joblib.load(MODEL_PATH)
        feature_columns = joblib.load(FEATURES_PATH)
        imputer         = joblib.load(IMPUTER_PATH)
        print("ML artifacts loaded successfully")
        print(f"   Features : {len(feature_columns)} columns")
        print(f"   Features : {feature_columns}")
    except Exception as e:
        print(f" Error loading ML artifacts: {e}")
        raise
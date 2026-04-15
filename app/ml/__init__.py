import os
import joblib
import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'thyroid_model.pkl')
FEATURES_PATH = os.path.join(os.path.dirname(__file__), 'feature_columns.pkl')
ENCODERS_PATH = os.path.join(os.path.dirname(__file__), 'label_encoders.pkl')

model = None
feature_columns = None
label_encoders = None

def load_ml_artifacts():
    global model, feature_columns, label_encoders
    try:
        model = joblib.load(MODEL_PATH)
        feature_columns = joblib.load(FEATURES_PATH)
        label_encoders = joblib.load(ENCODERS_PATH)
        print("✅ ML artifacts loaded successfully")
        print(f"   Features: {len(feature_columns)} columns")
        print(f"   Encoders: {list(label_encoders.keys())}")
    except Exception as e:
        print(f"❌ Error loading ML artifacts: {e}")
        raise
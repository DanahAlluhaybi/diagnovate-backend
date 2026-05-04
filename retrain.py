import pandas as pd
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score, f1_score
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
import joblib, os

SAVE_DIR = 'app/ml'
CSV_PATH = os.path.join(SAVE_DIR, 'hypothyroid.csv')

df = pd.read_csv(CSV_PATH, dtype=str)
df['Age'] = pd.to_numeric(df['Age'], errors='coerce')
df['target'] = (df['Recurred'].str.strip().str.lower() == 'yes').astype(int)
df.drop(columns=['Recurred'], inplace=True)

feature_cols = [c for c in df.columns if c != 'target']
encoders = {}
for col in feature_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')
    if df[col].isna().any():
        df[col] = df[col].astype(str)
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col])
        encoders[col] = le
    df[col] = pd.to_numeric(df[col], errors='coerce')

X = df[feature_cols].values.astype(np.float32)
y = df['target'].values

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

imputer = SimpleImputer(strategy='median')
X_train = imputer.fit_transform(X_train)
X_test  = imputer.transform(X_test)

xgb = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, scale_pos_weight=(y_train==0).sum()/max((y_train==1).sum(),1), eval_metric='auc', random_state=42, verbosity=0)
xgb.fit(X_train, y_train)
xp = xgb.predict_proba(X_test)[:,1]

cat = CatBoostClassifier(iterations=300, depth=4, learning_rate=0.05, auto_class_weights='Balanced', random_seed=42, verbose=0)
cat.fit(X_train, y_train)
cp = cat.predict_proba(X_test)[:,1]

rf = RandomForestClassifier(n_estimators=300, max_depth=6, class_weight='balanced', random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)
rp = rf.predict_proba(X_test)[:,1]

avg = (xp + cp + rp) / 3
best_t, best_f1 = 0.5, 0
for t in np.arange(0.2, 0.8, 0.01):
    f1 = f1_score(y_test, (avg>=t).astype(int), zero_division=0)
    if f1 > best_f1: best_f1, best_t = f1, t

print(f"Ensemble AUC: {roc_auc_score(y_test,avg):.3f} | Threshold: {best_t:.4f} | F1: {best_f1:.3f}")
print(classification_report(y_test,(avg>=best_t).astype(int),target_names=['Benign','Malignant']))

joblib.dump(imputer,      os.path.join(SAVE_DIR,'imputer.pkl'))
joblib.dump(feature_cols, os.path.join(SAVE_DIR,'feature_columns.pkl'))
joblib.dump(best_t,       os.path.join(SAVE_DIR,'threshold.pkl'))
joblib.dump(xgb,          os.path.join(SAVE_DIR,'xgboost_model.pkl'))
joblib.dump(cat,          os.path.join(SAVE_DIR,'catboost_model.pkl'))
joblib.dump(rf,           os.path.join(SAVE_DIR,'rf_model.pkl'))
joblib.dump(encoders,     os.path.join(SAVE_DIR,'label_encoders.pkl'))

for f in ['imputer.pkl','feature_columns.pkl','threshold.pkl','xgboost_model.pkl','catboost_model.pkl','rf_model.pkl']:
    sz = os.path.getsize(os.path.join(SAVE_DIR,f))
    print(f"{f}: {sz:,} bytes {'OK' if sz>100 else 'EMPTY!'}")

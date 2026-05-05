import pandas as pd
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score, f1_score, accuracy_score
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
import joblib, os, sklearn
print(f"sklearn version: {sklearn.__version__}")

SAVE_DIR = 'app/ml'
df = pd.read_csv(os.path.join(SAVE_DIR, 'hypothyroid.csv'))
df['target'] = (df['Recurred'].str.strip().str.lower() == 'yes').astype(int)
df.drop(columns=['Recurred'], inplace=True)

ordinal_maps = {
    'Gender': ['F','M'],
    'Smoking': ['No','Yes'],
    'Hx Smoking': ['No','Yes'],
    'Hx Radiothreapy': ['No','Yes'],
    'Thyroid Function': ['Euthyroid','Subclinical Hypothyroidism','Clinical Hypothyroidism','Subclinical Hyperthyroidism','Clinical Hyperthyroidism'],
    'Physical Examination': ['Normal','Single nodular goiter-left','Single nodular goiter-right','Multinodular goiter','Diffuse goiter'],
    'Adenopathy': ['No','Left','Right','Posterior','Bilateral','Extensive'],
    'Pathology': ['Micropapillary','Papillary','Follicular','Hurthel cell'],
    'Focality': ['Uni-Focal','Multi-Focal'],
    'Risk': ['Low','Intermediate','High'],
    'T': ['T1a','T1b','T2','T3a','T3b','T4a','T4b'],
    'N': ['N0','N1a','N1b'],
    'M': ['M0','M1'],
    'Stage': ['I','II','III','IVA','IVB'],
    'Response': ['Excellent','Indeterminate','Biochemical Incomplete','Structural Incomplete'],
}

for col, order in ordinal_maps.items():
    df[col] = pd.Categorical(df[col], categories=order, ordered=True).codes

feature_cols = [c for c in df.columns if c != 'target']
X = df[feature_cols].values.astype(np.float32)
y = df['target'].values

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

imputer = SimpleImputer(strategy='median')
X_train = imputer.fit_transform(X_train)
X_test = imputer.transform(X_test)

xgb = XGBClassifier(n_estimators=500, max_depth=5, learning_rate=0.03, subsample=0.8, colsample_bytree=0.8, min_child_weight=2, scale_pos_weight=(y_train==0).sum()/max((y_train==1).sum(),1), eval_metric='auc', random_state=42, verbosity=0)
xgb.fit(X_train, y_train)
xp = xgb.predict_proba(X_test)[:,1]
print(f"XGBoost AUC: {roc_auc_score(y_test, xp):.3f}")

cat = CatBoostClassifier(iterations=500, depth=6, learning_rate=0.03, auto_class_weights='Balanced', l2_leaf_reg=5, random_seed=42, verbose=0)
cat.fit(X_train, y_train)
cp = cat.predict_proba(X_test)[:,1]
print(f"CatBoost AUC: {roc_auc_score(y_test, cp):.3f}")

rf = RandomForestClassifier(n_estimators=500, max_depth=8, min_samples_leaf=2, class_weight='balanced', random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)
rp = rf.predict_proba(X_test)[:,1]
print(f"RandomForest AUC: {roc_auc_score(y_test, rp):.3f}")

avg = (xp + cp + rp) / 3
best_t, best_f1 = 0.5, 0
for t in np.arange(0.1, 0.9, 0.01):
    f1 = f1_score(y_test, (avg>=t).astype(int), zero_division=0)
    if f1 > best_f1: best_f1, best_t = f1, t

print(f"Ensemble AUC: {roc_auc_score(y_test, avg):.3f} | Accuracy: {accuracy_score(y_test,(avg>=best_t).astype(int))*100:.1f}% | Threshold: {best_t:.2f}")
print(classification_report(y_test,(avg>=best_t).astype(int),target_names=['No Recurrence','Recurrence']))

joblib.dump(imputer, os.path.join(SAVE_DIR,'imputer.pkl'))
joblib.dump(feature_cols, os.path.join(SAVE_DIR,'feature_columns.pkl'))
joblib.dump(best_t, os.path.join(SAVE_DIR,'threshold.pkl'))
joblib.dump(xgb, os.path.join(SAVE_DIR,'xgboost_model.pkl'))
joblib.dump(cat, os.path.join(SAVE_DIR,'catboost_model.pkl'))
joblib.dump(rf, os.path.join(SAVE_DIR,'rf_model.pkl'))
joblib.dump(ordinal_maps, os.path.join(SAVE_DIR,'label_encoders.pkl'))
print("✅ All models saved!")

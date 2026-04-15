import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
import joblib
import os

# ── تحميل البيانات ──
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hypothyroid.csv')
df = pd.read_csv(CSV_PATH, sep='\t')
print(f"✅ Loaded: {df.shape[0]} rows, {df.shape[1]} columns")

# ── تنظيف البيانات ──
drop_cols = ['patient_id', 'referral_source']
df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True)

# ── تبسيط عمود target إلى 3 فئات فقط ──
# الداتاست يستخدم كودات: '-' = Normal, أي شيء ثاني = مشكلة
def simplify_target(val):
    val = str(val).replace('|', '').strip()
    if val == '-':
        return 'Normal'
    elif val in ['A', 'B', 'C', 'D']:
        return 'Hyperthyroid'
    else:
        return 'Hypothyroid'

df['target'] = df['target'].astype(str).str.replace(r'\|.*', '', regex=True).str.strip()
df['target'] = df['target'].apply(simplify_target)

print(f"\nSimplified classes: {df['target'].unique()}")
print(f"Class distribution:\n{df['target'].value_counts()}")

# ── استبدال القيم الناقصة ──
df.replace('?', np.nan, inplace=True)

# ── تحويل الأعمدة الرقمية ──
for col in df.columns:
    if col == 'target':
        continue
    try:
        df[col] = pd.to_numeric(df[col])
    except (ValueError, TypeError):
        pass

# ── ملء القيم الناقصة ──
for col in df.columns:
    if col == 'target':
        continue
    if df[col].dtype in ['float64', 'int64']:
        df[col] = df[col].fillna(df[col].median())
    else:
        df[col] = df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else 'f')

# ── تحويل الأعمدة النصية لأرقام ──
label_encoders = {}
for col in df.select_dtypes(include=['object', 'str']).columns:
    if col == 'target':
        continue
    le = LabelEncoder()
    df[col] = le.fit_transform(df[col].astype(str))
    label_encoders[col] = le

# ── تحويل عمود الـ target ──
target_le = LabelEncoder()
df['target'] = target_le.fit_transform(df['target'])
label_encoders['target'] = target_le

print(f"\nFinal classes: {target_le.classes_}")

# ── تحديد الـ Features والـ Target ──
X = df.drop('target', axis=1)
y = df['target']
print(f"Features ({len(X.columns)}): {X.columns.tolist()}")

# ── تقسيم البيانات ──
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# ── تدريب الموديل ──
print("\n⏳ Training model...")
model = XGBClassifier(
    n_estimators=200,
    max_depth=5,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
    use_label_encoder=False,
    eval_metric='mlogloss',
    random_state=42
)
model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

# ── تقييم الموديل ──
y_pred = model.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"\n✅ Accuracy: {acc * 100:.2f}%")
print(classification_report(y_test, y_pred, target_names=target_le.classes_))

# ── حفظ الموديل ──
save_dir = os.path.dirname(os.path.abspath(__file__))
joblib.dump(model,              os.path.join(save_dir, 'thyroid_model.pkl'))
joblib.dump(label_encoders,     os.path.join(save_dir, 'label_encoders.pkl'))
joblib.dump(X.columns.tolist(), os.path.join(save_dir, 'feature_columns.pkl'))

print("\n✅ Model saved!")
print("   → app/ml/thyroid_model.pkl")
print("   → app/ml/label_encoders.pkl")
print("   → app/ml/feature_columns.pkl")
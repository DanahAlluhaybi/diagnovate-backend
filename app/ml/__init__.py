def predict_lab(patient_data: dict) -> dict:
    if not ml_ready:
        raise RuntimeError("ML models not loaded")
    import pandas as pd

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
    X = imputer.transform(df)

    xgb_prob = xgb_model.predict_proba(X)[0][1]
    cat_prob  = cat_model.predict_proba(X)[0][1]
    rf_prob   = rf_model.predict_proba(X)[0][1]

    xgb_pred = "Malignant" if xgb_prob >= threshold else "Benign"
    cat_pred  = "Malignant" if cat_prob  >= threshold else "Benign"
    rf_pred   = "Malignant" if rf_prob   >= threshold else "Benign"

    majority = "Malignant" if [xgb_pred, cat_pred, rf_pred].count("Malignant") >= 2 else "Benign"

    # ✅ الإصلاح: كل نموذج يعطي confidence للـclass اللي تنبأ به
    def _conf(prob, pred):
        return round(prob * 100, 1) if pred == "Malignant" else round((1 - prob) * 100, 1)

    xgb_conf = _conf(xgb_prob, xgb_pred)
    cat_conf  = _conf(cat_prob,  cat_pred)
    rf_conf   = _conf(rf_prob,   rf_pred)

    # ✅ الإصلاح: الـconfidence الكلي = متوسط confidence النماذج التي وافقت الأغلبية
    majority_probs = []
    if xgb_pred == majority:
        majority_probs.append(xgb_prob if majority == "Malignant" else 1 - xgb_prob)
    if cat_pred == majority:
        majority_probs.append(cat_prob  if majority == "Malignant" else 1 - cat_prob)
    if rf_pred == majority:
        majority_probs.append(rf_prob   if majority == "Malignant" else 1 - rf_prob)

    overall_confidence = round(sum(majority_probs) / len(majority_probs) * 100, 1)

    return {
        "majority_result": majority,
        "confidence": overall_confidence,
        "models": {
            "XGBoost":       {"result": xgb_pred, "confidence": xgb_conf},
            "CatBoost":      {"result": cat_pred,  "confidence": cat_conf},
            "Random Forest": {"result": rf_pred,   "confidence": rf_conf},
        }
    }
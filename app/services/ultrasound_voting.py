"""
app/services/ultrasound_voting.py
Majority Voting — Thyroid Ultrasound Ensemble (3 models)

Flow:
    Image → EfficientNet-B4+YOLO (existing)  → vote
           → Swin Transformer    (new)        → vote
           → DenseNet-121 v2     (new)        → vote
                    ↓
            Majority (≥2/3) → Final Result
            Tie → Malignant (patient safety)
"""

from app.services.swin_service              import predict_swin
from app.services.densenet_service          import predict_densenet
from app.services.efficientnet_yolo_service import predict_efficientnet_yolo


def _format_efficientnet(result) -> dict:
    if result is None:
        return {
            "model": "EfficientNet-B4 + YOLO", "vote": -1,
            "label": "unavailable", "confidence": 0.0,
            "probs": {"benign": 0.0, "malignant": 0.0},
        }
    vote  = int(result.get("vote", -1))
    label = "malignant" if vote == 1 else ("benign" if vote == 0 else "unavailable")
    return {
        "model":      "EfficientNet-B4 + YOLO",
        "vote":       vote,
        "label":      label,
        "confidence": float(result.get("confidence", 0.0)),
        "probs":      result.get("probs", {"benign": 0.0, "malignant": 0.0}),
    }


def _majority_vote(results: list) -> dict:
    valid           = [r for r in results if r["vote"] in (0, 1)]
    n               = len(valid)
    if n == 0:
        return {"final_vote": -1, "malignant_count": 0, "benign_count": 0, "valid_votes": 0}
    mal             = sum(1 for r in valid if r["vote"] == 1)
    ben             = n - mal
    final_vote      = 1 if mal >= ben else 0   # tie → malignant (safety)
    return {"final_vote": final_vote, "malignant_count": mal, "benign_count": ben, "valid_votes": n}


def run_ultrasound_voting(image_bytes: bytes, efficientnet_result=None, selected_model: str = "majority") -> dict:
    errors = []
    single = selected_model.lower().strip() not in ("majority", "majority voting", "")

    if efficientnet_result is None:
        try:
            efficientnet_result = predict_efficientnet_yolo(image_bytes)
        except Exception as e:
            errors.append(f"EfficientNet+YOLO: {e}")

    eff_result = _format_efficientnet(efficientnet_result)

    if single:
        model_key = selected_model.lower()
        if "swin" in model_key:
            try:
                swin_result = predict_swin(image_bytes)
            except Exception as e:
                errors.append(f"Swin: {e}")
                swin_result = {"model": "Swin Transformer", "vote": -1, "confidence": 0.0}
            result     = swin_result
            all_results = [swin_result]
        elif "dense" in model_key:
            try:
                dense_result = predict_densenet(image_bytes)
            except Exception as e:
                errors.append(f"DenseNet: {e}")
                dense_result = {"model": "DenseNet-121", "vote": -1, "confidence": 0.0}
            result      = dense_result
            all_results = [dense_result]
        else:
            result      = eff_result
            all_results = [eff_result]

        vote       = result.get("vote", -1)
        confidence = float(result.get("confidence", 0.0))
        if   vote == 1: final_prediction = "Malignant"
        elif vote == 0: final_prediction = "Benign"
        else:           final_prediction = "Inconclusive"

        return {
            "final_prediction": final_prediction,
            "final_vote":       vote,
            "confidence_score": round(confidence * 100, 2) if confidence <= 1 else round(confidence, 2),
            "vote_summary":     f"Single model: {result.get('model', selected_model)}",
            "unanimous":        True,
            "models":           all_results,
            "errors":           errors if errors else None,
            "disclaimer":       "AI-assisted result — intended to support, not replace, "
                                "clinical judgment. Final diagnosis must be confirmed by a physician.",
        }

    # Majority voting
    try:
        swin_result = predict_swin(image_bytes)
    except Exception as e:
        errors.append(f"Swin: {e}")
        swin_result = {"model": "Swin Transformer", "vote": -1, "label": "error",
                       "confidence": 0.0, "probs": {"benign": 0.0, "malignant": 0.0}}

    try:
        dense_result = predict_densenet(image_bytes)
    except Exception as e:
        errors.append(f"DenseNet: {e}")
        dense_result = {"model": "DenseNet-121", "vote": -1, "label": "error",
                        "confidence": 0.0, "probs": {"benign": 0.0, "malignant": 0.0}}

    all_results = [eff_result, swin_result, dense_result]
    vote_info   = _majority_vote(all_results)
    final_vote  = vote_info["final_vote"]

    winning  = [r for r in all_results if r["vote"] == final_vote]
    avg_conf = sum(r["confidence"] for r in winning) / len(winning) if winning else 0.0

    if   final_vote == 1: final_prediction = "Malignant"
    elif final_vote == 0: final_prediction = "Benign"
    else:                 final_prediction = "Inconclusive"

    mal   = vote_info["malignant_count"]
    ben   = vote_info["benign_count"]
    total = vote_info["valid_votes"]

    return {
        "final_prediction": final_prediction,
        "final_vote":       final_vote,
        "confidence_score": round(avg_conf * 100, 2),
        "vote_summary":     f"{mal}/{total} Malignant | {ben}/{total} Benign",
        "unanimous":        mal == total or ben == total,
        "models":           all_results,
        "errors":           errors if errors else None,
        "disclaimer":       "AI-assisted result — intended to support, not replace, "
                            "clinical judgment. Final diagnosis must be confirmed by a physician.",
    }

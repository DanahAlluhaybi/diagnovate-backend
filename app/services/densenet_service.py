"""
app/services/densenet_service.py
DenseNet-121 v2 — Thyroid Ultrasound Classifier
Architecture: densenet121 fine-tuned
Accuracy: 97.64% | AUC-ROC: 0.9979
"""

import io
import os
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image

MODEL_PATH  = os.path.join(os.path.dirname(__file__), '..', 'ml', 'densenet121_thyroid_v2_BEST.pth')
DEVICE      = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CLASS_NAMES = ["benign", "malignant"]

_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])


def _build_densenet(num_classes: int = 2) -> nn.Module:
    model = models.densenet121(weights=None)
    in_features = model.classifier.in_features  # 1024
    model.classifier = nn.Sequential(
        nn.Linear(in_features, 512),
        nn.BatchNorm1d(512),
        nn.ReLU(inplace=True),
        nn.Dropout(0.3),
        nn.Linear(512, 128),
        nn.ReLU(inplace=True),
        nn.Dropout(0.2),
        nn.Linear(128, num_classes),
    )
    return model


_densenet_model = None


def _load_model() -> nn.Module:
    global _densenet_model
    if _densenet_model is not None:
        return _densenet_model

    model = _build_densenet(num_classes=2).to(DEVICE)

    if not os.path.exists(MODEL_PATH):
        from huggingface_hub import hf_hub_download
        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError("HF_TOKEN env var not set and model not found locally")
        resolved = hf_hub_download(
            repo_id="iimvbii/diagnovate-models",
            filename="densenet121_thyroid_v2_BEST.pth",
            token=hf_token,
            local_dir=os.path.join(os.path.dirname(__file__), '..', 'ml'),
        )
        print(f"✅ DenseNet model downloaded from HuggingFace to {resolved}")

    checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)
    state_dict = checkpoint.get("model_state", checkpoint.get("model_state_dict", checkpoint))
    model.load_state_dict(state_dict)
    model.eval()

    _densenet_model = model
    print(f"✅ DenseNet-121 v2 loaded on {DEVICE}")
    return _densenet_model


def predict_densenet(image_bytes: bytes) -> dict:
    model  = _load_model()
    image  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = _transform(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        logits = model(tensor)
        probs  = torch.softmax(logits, dim=1)[0]

    benign_prob    = float(probs[0])
    malignant_prob = float(probs[1])
    pred_idx       = int(probs.argmax())

    return {
        "model":      "DenseNet-121",
        "vote":       pred_idx,
        "label":      CLASS_NAMES[pred_idx],
        "confidence": float(probs[pred_idx]),
        "probs": {
            "benign":    round(benign_prob,    4),
            "malignant": round(malignant_prob, 4),
        },
    }


def is_densenet_loaded() -> bool:
    return _densenet_model is not None


def preload_densenet() -> None:
    try:
        _load_model()
    except Exception as e:
        print(f"⚠️  DenseNet-121 failed to load: {e}")

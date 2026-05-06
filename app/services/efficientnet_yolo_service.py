"""
app/services/efficientnet_yolo_service.py
EfficientNet-B4 — Thyroid Ultrasound Classifier
Classifies full image directly (no YOLO dependency).
"""

import io
import os
import torch
import torch.nn as nn
import timm
from PIL import Image
from torchvision import transforms

EFFNET_PATH = os.path.join(os.path.dirname(__file__), '..', 'ml', 'thyroid_efficientnet.pth')
DEVICE      = torch.device("cpu")
CLASS_NAMES = ["benign", "malignant"]

_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

_effnet_model = None
_effnet_ready = False


def _load_effnet():
    global _effnet_model
    if _effnet_model is not None:
        return _effnet_model
    model = timm.create_model('efficientnet_b4', pretrained=False, num_classes=2, drop_rate=0.3)
    checkpoint = torch.load(EFFNET_PATH, map_location=DEVICE)
    if isinstance(checkpoint, dict):
        state = checkpoint.get("model_state", checkpoint.get("model_state_dict", checkpoint))
    else:
        state = checkpoint
    model.load_state_dict(state)
    model.eval()
    _effnet_model = model
    print("✅ EfficientNet loaded on cpu")
    return _effnet_model


def predict_efficientnet_yolo(image_bytes: bytes) -> dict:
    if not _effnet_ready:
        raise RuntimeError("Model not ready yet")
    model  = _load_effnet()
    image  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = _transform(image).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        probs = torch.softmax(model(tensor), dim=1)[0]
    pred = int(probs.argmax())
    return {
        "model"          : "EfficientNet+YOLO",
        "vote"           : pred,
        "label"          : CLASS_NAMES[pred],
        "confidence"     : float(probs[pred]),
        "nodule_detected": True,
        "probs"          : {"benign": round(float(probs[0]), 4), "malignant": round(float(probs[1]), 4)},
    }


def is_efficientnet_yolo_loaded() -> bool:
    return _effnet_model is not None


def preload_efficientnet_yolo() -> None:
    global _effnet_ready
    try:
        _load_effnet()
        _effnet_ready = True
    except Exception as e:
        print(f"⚠️  EfficientNet+YOLO failed to load: {e}")

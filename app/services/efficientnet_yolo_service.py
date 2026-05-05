"""
app/services/efficientnet_yolo_service.py
EfficientNet-B4 + YOLOv8 — Thyroid Ultrasound Classifier
Pipeline: YOLO detects nodule → crop → EfficientNet classifies crop
"""

import io
import os
import torch
import torch.nn as nn
import timm
from PIL import Image
from torchvision import transforms

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

YOLO_PATH   = os.path.join(os.path.dirname(__file__), '..', 'ml', 'thyroid_yolo.pt')
EFFNET_PATH = os.path.join(os.path.dirname(__file__), '..', 'ml', 'thyroid_efficientnet.pth')
DEVICE      = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CLASS_NAMES = ["benign", "malignant"]
PADDING     = 20

_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

_yolo_model   = None
_effnet_model = None


def _load_yolo():
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model
    if YOLO is None:
        raise RuntimeError("ultralytics/YOLO unavailable: libGL missing")
    try:
        from ultralytics import YOLO as _YOLO
        _yolo_model = _YOLO(YOLO_PATH)
    except Exception as e:
        raise RuntimeError(f"YOLO load failed: {e}")
    print(f"✅ YOLOv8 loaded from {YOLO_PATH}")
    return _yolo_model


def _load_effnet():
    global _effnet_model
    if _effnet_model is not None:
        return _effnet_model

    model = timm.create_model(
        "efficientnet_b4",
        pretrained=False,
        num_classes=2,
        drop_rate=0.3,
    ).to(DEVICE)

    checkpoint = torch.load(EFFNET_PATH, map_location=DEVICE)
    state_dict = checkpoint.get("model_state_dict", checkpoint)
    model.load_state_dict(state_dict)
    model.eval()

    _effnet_model = model
    print(f"✅ EfficientNet-B4 loaded on {DEVICE}")
    return _effnet_model


def _crop_largest_box(image: Image.Image, boxes) -> Image.Image:
    w, h   = image.size
    best   = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    x1, y1, x2, y2 = int(best[0]), int(best[1]), int(best[2]), int(best[3])
    x1 = max(0, x1 - PADDING)
    y1 = max(0, y1 - PADDING)
    x2 = min(w, x2 + PADDING)
    y2 = min(h, y2 + PADDING)
    return image.crop((x1, y1, x2, y2))


def predict_efficientnet_yolo(image_bytes: bytes) -> dict:
    yolo   = _load_yolo()
    effnet = _load_effnet()

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    results        = yolo(image, conf=0.3, verbose=False)
    boxes          = results[0].boxes.xyxy.cpu().tolist() if results[0].boxes else []
    nodule_detected = len(boxes) > 0

    crop = _crop_largest_box(image, boxes) if nodule_detected else image

    tensor = _transform(crop).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        logits = effnet(tensor)
        probs  = torch.softmax(logits, dim=1)[0]

    benign_prob    = float(probs[0])
    malignant_prob = float(probs[1])
    pred_idx       = int(probs.argmax())

    return {
        "model":           "EfficientNet+YOLO",
        "vote":            pred_idx,
        "label":           CLASS_NAMES[pred_idx],
        "confidence":      float(probs[pred_idx]),
        "nodule_detected": nodule_detected,
        "probs": {
            "benign":    round(benign_prob,    4),
            "malignant": round(malignant_prob, 4),
        },
    }


def is_efficientnet_yolo_loaded() -> bool:
    return _yolo_model is not None and _effnet_model is not None


def preload_efficientnet_yolo() -> None:
    try:
        _load_yolo()
        _load_effnet()
    except Exception as e:
        print(f"⚠️  EfficientNet+YOLO failed to load: {e}")

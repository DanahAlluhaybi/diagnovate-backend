"""
app/services/swin_service.py
Swin Transformer — Thyroid Ultrasound Classifier
Architecture: swin_base_patch4_window7_224
Accuracy: 96.85% | AUC-ROC: 0.9939
"""

import io
import os
import torch
import torch.nn as nn
import timm
from PIL import Image
from torchvision import transforms

MODEL_PATH  = os.path.join(os.path.dirname(__file__), '..', 'ml', 'swin_thyroid_BEST.pth')
DEVICE      = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CLASS_NAMES = ["benign", "malignant"]

_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])


class SwinThyroidClassifier(nn.Module):
    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.backbone = timm.create_model(
            "swin_base_patch4_window7_224",
            pretrained=False,
            num_classes=0,
            global_pool="avg",
        )
        in_feats = self.backbone.num_features  # 1024
        self.head = nn.Sequential(
            nn.LayerNorm(in_feats),
            nn.Linear(in_feats, 512), nn.GELU(), nn.Dropout(0.4),
            nn.Linear(512, 128),      nn.GELU(), nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.backbone(x))


_swin_model = None
_swin_ready = False


def _load_model() -> SwinThyroidClassifier:
    global _swin_model
    if _swin_model is not None:
        return _swin_model

    model = SwinThyroidClassifier(num_classes=2).to(DEVICE)

    if not os.path.exists(MODEL_PATH):
        from huggingface_hub import hf_hub_download
        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError("HF_TOKEN env var not set and model not found locally")
        resolved = hf_hub_download(
            repo_id="iimvbii/diagnovate-models",
            filename="swin_thyroid_BEST.pth",
            token=hf_token,
            local_dir=os.path.join(os.path.dirname(__file__), '..', 'ml'),
        )
        print(f"✅ Swin model downloaded from HuggingFace to {resolved}")

    checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)
    state_dict = checkpoint.get("model_state", checkpoint.get("model_state_dict", checkpoint))
    model.load_state_dict(state_dict)
    model.eval()

    _swin_model = model
    print(f"✅ Swin Transformer loaded on {DEVICE}")
    return _swin_model


def predict_swin(image_bytes: bytes) -> dict:
    if not _swin_ready:
        raise RuntimeError("Model not ready yet")
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
        "model":      "Swin Transformer",
        "vote":       pred_idx,
        "label":      CLASS_NAMES[pred_idx],
        "confidence": float(probs[pred_idx]),
        "probs": {
            "benign":    round(benign_prob,    4),
            "malignant": round(malignant_prob, 4),
        },
    }


def is_swin_loaded() -> bool:
    return _swin_model is not None


def preload_swin() -> None:
    global _swin_ready
    try:
        _load_model()
        _swin_ready = True
    except Exception as e:
        print(f"⚠️  Swin Transformer failed to load: {e}")

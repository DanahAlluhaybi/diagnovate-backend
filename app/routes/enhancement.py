import io
import base64
import numpy as np
import cv2
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from PIL import Image
import os

enhancement_bp = Blueprint('enhancement', __name__)

# ── Model state ───────────────────────────────────────────────────────────────
_sr_model     = None
_model_loaded = False
MODEL_PATH    = os.path.join(os.path.dirname(__file__), '..', 'ml', 'realesr-general-x4v3.pth')


def get_sr_model():
    """Lazy-load RealESRGAN. Falls back to Lanczos if torch/model unavailable."""
    global _sr_model, _model_loaded
    if _model_loaded:
        return _sr_model
    _model_loaded = True

    if not os.path.exists(MODEL_PATH):
        print(f"⚠️ SR model not found at {MODEL_PATH} — using Lanczos fallback")
        return None

    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F

        class SRVGGNetCompact(nn.Module):
            def __init__(self, num_in_ch=3, num_out_ch=3, num_feat=64,
                         num_conv=32, upscale=4, act_type='prelu'):
                super().__init__()
                self.upscale = upscale
                self.body    = nn.ModuleList()
                self.body.append(nn.Conv2d(num_in_ch, num_feat, 3, 1, 1))
                self.body.append(nn.PReLU(num_parameters=num_feat))
                for _ in range(num_conv):
                    self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
                    self.body.append(nn.PReLU(num_parameters=num_feat))
                self.body.append(nn.Conv2d(num_feat, num_out_ch * upscale * upscale, 3, 1, 1))
                self.upsampler = nn.PixelShuffle(upscale)

            def forward(self, x):
                out = x
                for layer in self.body:
                    out = layer(out)
                out = self.upsampler(out)
                base = F.interpolate(x, scale_factor=self.upscale, mode='nearest')
                return out + base

        net        = SRVGGNetCompact()
        state_dict = torch.load(MODEL_PATH, map_location='cpu')
        key        = 'params_ema' if 'params_ema' in state_dict else \
                     'params'     if 'params'     in state_dict else None
        net.load_state_dict(state_dict[key] if key else state_dict, strict=True)
        net.eval()
        _sr_model = net
        print("✅ RealESRGAN general-x4v3 loaded")
        return _sr_model

    except Exception as e:
        print(f"⚠️ RealESRGAN load failed: {e} — using Lanczos fallback")
        return None


# ── Processing steps ──────────────────────────────────────────────────────────

def apply_denoising(img: Image.Image) -> Image.Image:
    arr      = np.array(img)
    gray     = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=5,
                                         templateWindowSize=7, searchWindowSize=21)
    bilateral = cv2.bilateralFilter(denoised, d=7, sigmaColor=45, sigmaSpace=45)
    return Image.fromarray(cv2.cvtColor(bilateral, cv2.COLOR_GRAY2RGB))


def apply_realesrgan(img: Image.Image, model) -> Image.Image:
    import torch
    arr    = np.array(img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(np.transpose(arr, (2, 0, 1))).unsqueeze(0)
    with torch.no_grad():
        out = model(tensor)
    out_np = out.squeeze(0).permute(1, 2, 0).clamp(0, 1).numpy()
    return Image.fromarray((out_np * 255).astype(np.uint8))


def apply_lanczos(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img.resize((w * 4, h * 4), Image.LANCZOS)


def apply_clahe(img: Image.Image) -> Image.Image:
    arr        = np.array(img)
    lab        = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    l, a, b    = cv2.split(lab)
    clahe      = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
    l_enh      = clahe.apply(l)
    table      = np.array([((i / 255.0) ** (1 / 1.2)) * 255
                           for i in range(256)]).astype("uint8")
    l_final    = cv2.LUT(l_enh, table)
    result     = cv2.cvtColor(cv2.merge([l_final, a, b]), cv2.COLOR_LAB2RGB)
    return Image.fromarray(result)


def apply_sharpening(img: Image.Image) -> Image.Image:
    arr       = np.array(img).astype(np.float32)
    blurred   = cv2.GaussianBlur(arr, (0, 0), sigmaX=1.8)
    sharpened = cv2.addWeighted(arr, 1.5, blurred, -0.5, 0)
    return Image.fromarray(np.clip(sharpened, 0, 255).astype(np.uint8))


def full_pipeline(img: Image.Image) -> tuple[Image.Image, str]:
    img   = apply_denoising(img)
    model = get_sr_model()

    if model is not None:
        try:
            img       = apply_realesrgan(img, model)
            sr_method = "RealESRGAN x4v3"
        except Exception as e:
            print(f"⚠️ RealESRGAN inference failed: {e}")
            img       = apply_lanczos(img)
            sr_method = "Lanczos x4 (fallback)"
    else:
        img       = apply_lanczos(img)
        sr_method = "Lanczos x4"

    img = apply_clahe(img)
    img = apply_sharpening(img)
    return img, f"Denoising → {sr_method} → CLAHE → Sharpening"


def img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


# ── Endpoint ──────────────────────────────────────────────────────────────────

@enhancement_bp.route('/api/enhance', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True)
def enhance_image():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if 'image' not in request.files:
        return jsonify({'error': 'No image provided. Send as multipart/form-data with key "image"'}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # ✅ Validate file type
    allowed = {'image/jpeg', 'image/png', 'image/webp', 'image/bmp'}
    if file.content_type and file.content_type.lower() not in allowed:
        return jsonify({'error': f'Unsupported file type: {file.content_type}'}), 415

    try:
        img = Image.open(io.BytesIO(file.read()))
    except Exception:
        return jsonify({'error': 'Invalid or corrupted image file'}), 400

    if img.mode != 'RGB':
        img = img.convert('RGB')

    original_b64 = img_to_b64(img)

    # Cap input size to avoid OOM
    MAX_INPUT = 512
    if img.width > MAX_INPUT or img.height > MAX_INPUT:
        img.thumbnail((MAX_INPUT, MAX_INPUT), Image.LANCZOS)

    orig_w, orig_h = img.size

    try:
        enhanced_img, method_used = full_pipeline(img)
    except Exception as e:
        print(f"❌ Enhancement pipeline failed: {e}")
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500

    enhanced_b64 = img_to_b64(enhanced_img)
    enh_w, enh_h = enhanced_img.size

    return jsonify({
        'success':  True,
        'method':   method_used,
        'original': f'data:image/png;base64,{original_b64}',
        'enhanced': f'data:image/png;base64,{enhanced_b64}',
        'stats': {
            'original_size': f'{orig_w}x{orig_h}',
            'enhanced_size': f'{enh_w}x{enh_h}',
            'scale_factor':  f'{round(enh_w / orig_w, 1)}x',
        }
    }), 200

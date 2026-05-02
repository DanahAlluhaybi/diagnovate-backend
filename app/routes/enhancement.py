import io
import base64
import urllib.request
import numpy as np
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from PIL import Image
import os
import replicate
from app.models import db, Case
from app.utils.storage import upload_image

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
        print(f"SR model not found at {MODEL_PATH} -- using Lanczos fallback")
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
        print("RealESRGAN general-x4v3 loaded")
        return _sr_model

    except Exception as e:
        print(f"RealESRGAN load failed: {e} -- using Lanczos fallback")
        return None


# ── Processing steps ──────────────────────────────────────────────────────────

def apply_denoising(img: Image.Image) -> Image.Image:
    import cv2
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
    import cv2
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
    import cv2
    arr       = np.array(img).astype(np.float32)
    blurred   = cv2.GaussianBlur(arr, (0, 0), sigmaX=1.8)
    sharpened = cv2.addWeighted(arr, 1.5, blurred, -0.5, 0)
    return Image.fromarray(np.clip(sharpened, 0, 255).astype(np.uint8))


def run_replicate_upscale(image_bytes: bytes) -> bytes:
    b64 = base64.b64encode(image_bytes).decode('utf-8')
    data_url = f'data:image/png;base64,{b64}'
    output = replicate.run(
        "philz1337x/clarity-upscaler:9d74f57c1b6f406f3b48ae15ef6e8af22a0c4c3a1e756f73624b4cd7c32cb01",
        input={
            "image":        data_url,
            "scale_factor": 4,
            "resemblance":  0.6,
            "creativity":   0.35,
            "dynamic":      6,
            "sharpen":      2,
        }
    )
    url = output if isinstance(output, str) else output[0]
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def ultrasound_pipeline(img: Image.Image) -> tuple[Image.Image, str]:
    import cv2
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)

    # Denoise
    denoised = cv2.fastNlMeansDenoising(arr, None, h=2,
                                         templateWindowSize=7, searchWindowSize=21)

    # Morphological open+close blend
    kernel  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    opened  = cv2.morphologyEx(denoised, cv2.MORPH_OPEN,  kernel)
    closed  = cv2.morphologyEx(opened,   cv2.MORPH_CLOSE, kernel)
    blended = cv2.addWeighted(denoised, 0.75, closed, 0.25, 0)

    # CLAHE
    clahe     = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    equalized = clahe.apply(blended)

    # Convert to RGB for Replicate upscale
    pre_upscale = Image.fromarray(cv2.cvtColor(equalized, cv2.COLOR_GRAY2RGB))

    try:
        buf = io.BytesIO()
        pre_upscale.save(buf, format='PNG')
        upscaled_bytes = run_replicate_upscale(buf.getvalue())
        upscaled = Image.open(io.BytesIO(upscaled_bytes)).convert('RGB')
        sr_method = "Replicate Clarity Upscaler x4"
    except Exception as e:
        print(f"Replicate upscale failed: {e} -- using Lanczos fallback")
        w, h = pre_upscale.size
        upscaled = pre_upscale.resize((w * 4, h * 4), Image.LANCZOS)
        sr_method = "Lanczos x4 (fallback)"

    # Back to grayscale for remaining steps
    arr = cv2.cvtColor(np.array(upscaled), cv2.COLOR_RGB2GRAY)

    # Bilateral smooth
    bilateral = cv2.bilateralFilter(arr, d=5, sigmaColor=25, sigmaSpace=25)

    # Unsharp mask
    gauss     = cv2.GaussianBlur(bilateral.astype(np.float32), (0, 0), sigmaX=1.0)
    sharpened = cv2.addWeighted(bilateral.astype(np.float32), 1.2, gauss, -0.2, 0)
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

    # Gamma 1.08 LUT
    table = np.array([((i / 255.0) ** (1 / 1.08)) * 255
                      for i in range(256)]).astype(np.uint8)
    gamma_corrected = cv2.LUT(sharpened, table)

    out = Image.fromarray(cv2.cvtColor(gamma_corrected, cv2.COLOR_GRAY2RGB))
    return out, f"Denoise → Morph blend → CLAHE → {sr_method} → Bilateral → Unsharp → Gamma"


def full_pipeline(img: Image.Image, image_type: str = 'auto') -> tuple[Image.Image, str]:
    if image_type == 'ultrasound':
        return ultrasound_pipeline(img)

    # ct or auto: denoise → Replicate upscale → CLAHE → sharpening
    img = apply_denoising(img)

    try:
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        upscaled_bytes = run_replicate_upscale(buf.getvalue())
        img       = Image.open(io.BytesIO(upscaled_bytes)).convert('RGB')
        sr_method = "Replicate Clarity Upscaler x4"
    except Exception as e:
        print(f"Replicate upscale failed: {e} -- falling back to local pipeline")
        model = get_sr_model()
        if model is not None:
            try:
                img       = apply_realesrgan(img, model)
                sr_method = "RealESRGAN x4v3 (local fallback)"
            except Exception as e2:
                print(f"Local RealESRGAN failed: {e2} -- using Lanczos")
                img       = apply_lanczos(img)
                sr_method = "Lanczos x4 (fallback)"
        else:
            img       = apply_lanczos(img)
            sr_method = "Lanczos x4 (fallback)"

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

    file       = request.files['image']
    case_id    = request.form.get('case_id')
    image_type = request.form.get('image_type', 'auto')
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
        enhanced_img, method_used = full_pipeline(img, image_type)
    except Exception as e:
        print(f"Enhancement pipeline failed: {e}")
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500

    enhanced_b64 = img_to_b64(enhanced_img)
    enh_w, enh_h = enhanced_img.size

    db_saved = False
    if case_id:
        case = Case.query.filter_by(case_id=case_id).first()
        if case:
            buf = io.BytesIO()
            enhanced_img.save(buf, format='PNG')
            buf.seek(0)
            cloudinary_url = upload_image(buf)
            case.enhanced_image_path = cloudinary_url
            case.updated_at = datetime.utcnow()
            db.session.commit()
            db_saved = True

    return jsonify({
        'success':  True,
        'method':   method_used,
        'original': f'data:image/png;base64,{original_b64}',
        'enhanced': f'data:image/png;base64,{enhanced_b64}',
        'db_saved': db_saved,
        'stats': {
            'original_size': f'{orig_w}x{orig_h}',
            'enhanced_size': f'{enh_w}x{enh_h}',
            'scale_factor':  f'{round(enh_w / orig_w, 1)}x',
        }
    }), 200
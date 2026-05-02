"""
Image Enhancement — Ultrasound only (RealESRGAN + CLAHE + Denoising + Sharpening).
MRI / X-Ray references removed. Pipeline focuses on thyroid ultrasound scans.
"""
import io
import base64
import numpy as np
import cv2
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from PIL import Image
import os

enhancement_bp = Blueprint('enhancement', __name__)

_ort_session  = None
_model_loaded = False

MODEL_PATH = os.path.join(os.path.dirname(__file__), "realesr-general-x4v3.pth")


# ── Model loader (lazy) ────────────────────────────────────────────────────────
def get_model():
    global _ort_session, _model_loaded
    if _model_loaded:
        return _ort_session
    try:
        import torch
        from torch import nn
        import torch.nn.functional as F

        class SRVGGNetCompact(nn.Module):
            def __init__(self, num_in_ch=3, num_out_ch=3, num_feat=64,
                         num_conv=32, upscale=4, act_type='prelu'):
                super().__init__()
                self.num_in_ch  = num_in_ch
                self.num_out_ch = num_out_ch
                self.num_feat   = num_feat
                self.num_conv   = num_conv
                self.upscale    = upscale
                self.act_type   = act_type

                self.body = nn.ModuleList()
                self.body.append(nn.Conv2d(num_in_ch, num_feat, 3, 1, 1))

                def _act():
                    if act_type == 'relu':      return nn.ReLU(inplace=True)
                    if act_type == 'prelu':     return nn.PReLU(num_parameters=num_feat)
                    if act_type == 'leakyrelu': return nn.LeakyReLU(0.1, inplace=True)

                self.body.append(_act())
                for _ in range(num_conv):
                    self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
                    self.body.append(_act())

                self.body.append(nn.Conv2d(num_feat, num_out_ch * upscale * upscale, 3, 1, 1))
                self.upsampler = nn.PixelShuffle(upscale)

            def forward(self, x):
                out = x
                for layer in self.body:
                    out = layer(out)
                out  = self.upsampler(out)
                base = F.interpolate(x, scale_factor=self.upscale, mode='nearest')
                return out + base

        model_net = SRVGGNetCompact(
            num_in_ch=3, num_out_ch=3,
            num_feat=64, num_conv=32,
            upscale=4, act_type='prelu'
        )
        state_dict = torch.load(MODEL_PATH, map_location='cpu')
        key = 'params_ema' if 'params_ema' in state_dict else ('params' if 'params' in state_dict else None)
        model_net.load_state_dict(state_dict[key] if key else state_dict, strict=True)
        model_net.eval()

        _ort_session  = model_net
        _model_loaded = True
        print("✅ RealESRGAN general-x4v3 loaded")
        return _ort_session

    except Exception as e:
        print(f"⚠️ RealESRGAN failed to load: {e} — using Lanczos fallback")
        _model_loaded = True
        _ort_session  = None
        return None


# ── Pipeline steps ─────────────────────────────────────────────────────────────
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


def apply_denoising(img: Image.Image) -> Image.Image:
    arr      = np.array(img)
    gray     = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=5,
                                         templateWindowSize=7, searchWindowSize=21)
    bilat    = cv2.bilateralFilter(denoised, d=7, sigmaColor=45, sigmaSpace=45)
    return Image.fromarray(cv2.cvtColor(bilat, cv2.COLOR_GRAY2RGB))


def apply_clahe(img: Image.Image) -> Image.Image:
    arr     = np.array(img)
    lab     = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe   = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
    l_enh   = clahe.apply(l)
    table   = np.array([((i / 255.0) ** (1 / 1.2)) * 255 for i in range(256)]).astype("uint8")
    l_final = cv2.LUT(l_enh, table)
    result  = cv2.cvtColor(cv2.merge([l_final, a, b]), cv2.COLOR_LAB2RGB)
    return Image.fromarray(result)


def apply_sharpening(img: Image.Image) -> Image.Image:
    arr      = np.array(img).astype(np.float32)
    blurred  = cv2.GaussianBlur(arr, (0, 0), sigmaX=1.8)
    sharp    = cv2.addWeighted(arr, 1.5, blurred, -0.5, 0)
    return Image.fromarray(np.clip(sharp, 0, 255).astype(np.uint8))


def full_enhancement_pipeline(img: Image.Image) -> tuple:
    """Returns (enhanced_image, sr_method_description)."""
    img = apply_denoising(img)

    model = get_model()
    if model is not None:
        try:
            img       = apply_realesrgan(img, model)
            sr_method = "RealESRGAN general-x4v3"
        except Exception as e:
            print(f"⚠️ RealESRGAN inference error: {e} — falling back to Lanczos")
            img       = apply_lanczos(img)
            sr_method = "Lanczos x4 (fallback)"
    else:
        img       = apply_lanczos(img)
        sr_method = "Lanczos x4 (fallback)"

    img = apply_clahe(img)
    img = apply_sharpening(img)
    return img, sr_method


def pil_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


# ── Route ──────────────────────────────────────────────────────────────────────
@enhancement_bp.route('/api/enhance', methods=['POST', 'OPTIONS'])
@jwt_required()
def enhance():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    # Validate: only accept common ultrasound image formats
    allowed = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    ext     = os.path.splitext(file.filename.lower())[1]
    if ext not in allowed:
        return jsonify({'error': f'Unsupported file type {ext}. Upload a PNG or JPEG ultrasound image.'}), 400

    try:
        raw   = file.read()
        img   = Image.open(io.BytesIO(raw)).convert('RGB')
        orig_b64 = pil_to_base64(img)

        enhanced, sr_method = full_enhancement_pipeline(img)
        enh_b64  = pil_to_base64(enhanced)

        return jsonify({
            'success':          True,
            'original_image':   orig_b64,
            'enhanced_image':   enh_b64,
            'sr_method':        sr_method,
            'original_size':    {'width': img.size[0],      'height': img.size[1]},
            'enhanced_size':    {'width': enhanced.size[0], 'height': enhanced.size[1]},
            'scan_type':        'Ultrasound',
        }), 200

    except Exception as e:
        print(f"ERROR in enhance: {e}")
        return jsonify({'error': str(e)}), 500
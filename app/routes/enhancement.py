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


def get_model():
    global _ort_session, _model_loaded
    if _model_loaded:
        return _ort_session
    try:
        import torch
        from torch import nn
        import torch.nn.functional as F

        # SRVGGNetCompact architecture
        class SRVGGNetCompact(nn.Module):
            def __init__(self, num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4, act_type='prelu'):
                super().__init__()
                self.num_in_ch  = num_in_ch
                self.num_out_ch = num_out_ch
                self.num_feat   = num_feat
                self.num_conv   = num_conv
                self.upscale    = upscale
                self.act_type   = act_type

                self.body = nn.ModuleList()
                self.body.append(nn.Conv2d(num_in_ch, num_feat, 3, 1, 1))
                if act_type == 'relu':
                    activation = nn.ReLU(inplace=True)
                elif act_type == 'prelu':
                    activation = nn.PReLU(num_parameters=num_feat)
                elif act_type == 'leakyrelu':
                    activation = nn.LeakyReLU(negative_slope=0.1, inplace=True)
                self.body.append(activation)

                for _ in range(num_conv):
                    self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
                    if act_type == 'relu':
                        activation = nn.ReLU(inplace=True)
                    elif act_type == 'prelu':
                        activation = nn.PReLU(num_parameters=num_feat)
                    elif act_type == 'leakyrelu':
                        activation = nn.LeakyReLU(negative_slope=0.1, inplace=True)
                    self.body.append(activation)

                self.body.append(nn.Conv2d(num_feat, num_out_ch * upscale * upscale, 3, 1, 1))
                self.upsampler = nn.PixelShuffle(upscale)

            def forward(self, x):
                out = x
                for i in range(0, len(self.body)):
                    out = self.body[i](out)
                out = self.upsampler(out)
                base = F.interpolate(x, scale_factor=self.upscale, mode='nearest')
                out += base
                return out

        model = SRVGGNetCompact(
            num_in_ch=3, num_out_ch=3,
            num_feat=64, num_conv=32,
            upscale=4, act_type='prelu'
        )

        state_dict = torch.load(MODEL_PATH, map_location='cpu')
        if 'params' in state_dict:
            model.load_state_dict(state_dict['params'], strict=True)
        elif 'params_ema' in state_dict:
            model.load_state_dict(state_dict['params_ema'], strict=True)
        else:
            model.load_state_dict(state_dict, strict=True)

        model.eval()
        _ort_session  = model
        _model_loaded = True
        print("✅ RealESRGAN general-x4v3 loaded")
        return _ort_session

    except Exception as e:
        print(f"⚠️ Model failed: {e} — using Lanczos fallback")
        _model_loaded = True
        _ort_session  = None
        return None


# ─── RealESRGAN inference ─────────────────────────────────────────────────────
def apply_realesrgan(img: Image.Image, model) -> Image.Image:
    import torch
    img_np     = np.array(img).astype(np.float32) / 255.0
    img_tensor = torch.from_numpy(np.transpose(img_np, (2, 0, 1))).unsqueeze(0)

    with torch.no_grad():
        output = model(img_tensor)

    out_np = output.squeeze(0).permute(1, 2, 0).clamp(0, 1).numpy()
    return Image.fromarray((out_np * 255).astype(np.uint8))


# ─── Lanczos fallback ─────────────────────────────────────────────────────────
def apply_lanczos(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img.resize((w * 4, h * 4), Image.LANCZOS)


# ─── Denoising ────────────────────────────────────────────────────────────────
def apply_denoising(img: Image.Image) -> Image.Image:
    img_np    = np.array(img)
    gray      = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    denoised  = cv2.fastNlMeansDenoising(gray, None, h=5,
                                          templateWindowSize=7,
                                          searchWindowSize=21)
    bilateral = cv2.bilateralFilter(denoised, d=7, sigmaColor=45, sigmaSpace=45)
    return Image.fromarray(cv2.cvtColor(bilateral, cv2.COLOR_GRAY2RGB))


# ─── CLAHE ────────────────────────────────────────────────────────────────────
def apply_clahe(img: Image.Image) -> Image.Image:
    img_np  = np.array(img)
    lab     = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe   = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
    l_enh   = clahe.apply(l)
    table   = np.array([((i/255.0)**(1/1.2))*255 for i in range(256)]).astype("uint8")
    l_final = cv2.LUT(l_enh, table)
    result  = cv2.cvtColor(cv2.merge([l_final, a, b]), cv2.COLOR_LAB2RGB)
    return Image.fromarray(result)


# ─── Sharpening ───────────────────────────────────────────────────────────────
def apply_sharpening(img: Image.Image) -> Image.Image:
    img_np    = np.array(img).astype(np.float32)
    blurred   = cv2.GaussianBlur(img_np, (0, 0), sigmaX=1.8)
    sharpened = cv2.addWeighted(img_np, 1.5, blurred, -0.5, 0)
    return Image.fromarray(np.clip(sharpened, 0, 255).astype(np.uint8))


# ─── Pipeline ─────────────────────────────────────────────────────────────────
def full_enhancement_pipeline(img: Image.Image) -> tuple:
    img = apply_denoising(img)

    model = get_model()
    if model is not None:
        try:
            img       = apply_realesrgan(img, model)
            sr_method = "RealESRGAN general-x4v3"
        except Exception as e:
            print(f"⚠️ RealESRGAN inference failed: {e}")
            img       = apply_lanczos(img)
            sr_method = "Lanczos x4"
    else:
        img       = apply_lanczos(img)
        sr_method = "Lanczos x4"

    img = apply_clahe(img)
    img = apply_sharpening(img)
    return img, f"Denoising → {sr_method} → CLAHE → Sharpening"


# ─── Endpoint ─────────────────────────────────────────────────────────────────
@enhancement_bp.route('/api/enhance', methods=['POST'])
@jwt_required(optional=True)
def enhance_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        img = Image.open(io.BytesIO(file.read()))
    except Exception:
        return jsonify({'error': 'Invalid image file'}), 400

    if img.mode != 'RGB':
        img = img.convert('RGB')

    orig_buf = io.BytesIO()
    img.save(orig_buf, format='PNG')
    original_b64 = base64.b64encode(orig_buf.getvalue()).decode('utf-8')

    max_input = 256
    if img.width > max_input or img.height > max_input:
        img.thumbnail((max_input, max_input), Image.LANCZOS)

    orig_w, orig_h = img.size

    try:
        enhanced_img, method_used = full_enhancement_pipeline(img)
    except Exception as e:
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500

    enh_buf = io.BytesIO()
    enhanced_img.save(enh_buf, format='PNG')
    enhanced_b64 = base64.b64encode(enh_buf.getvalue()).decode('utf-8')

    enh_w, enh_h = enhanced_img.size

    return jsonify({
        'success':  True,
        'method':   method_used,
        'use_ai':   True,
        'original': f'data:image/png;base64,{original_b64}',
        'enhanced': f'data:image/png;base64,{enhanced_b64}',
        'stats': {
            'original_size': f'{orig_w}x{orig_h}',
            'enhanced_size': f'{enh_w}x{enh_h}',
            'scale_factor':  f'{round(enh_w/orig_w, 1)}x'
        }
    }), 200
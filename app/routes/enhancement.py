import io
import base64
import numpy as np
import cv2
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from PIL import Image, ImageFilter, ImageEnhance

enhancement_bp = Blueprint('enhancement', __name__)

# ─── كاش الموديل ─────────────────────────────────────────────────────────────
_model = None
_model_loaded = False


def get_super_image_model():
    """يحمّل موديل DRLN من super-image مرة وحدة ويحتفظ فيه"""
    global _model, _model_loaded

    if _model_loaded:
        return _model

    try:
        from super_image import DrlnModel
        _model = DrlnModel.from_pretrained('eugenesiow/drln-bam', scale=4)
        _model.eval()
        _model_loaded = True
        print("✅ DRLN super-image model loaded successfully")
        return _model

    except Exception as e:
        _model_loaded = True
        _model = None
        print(f"⚠️ super-image failed to load: {e} — falling back to classic pipeline")
        return None


# ─── 1. Super Resolution بـ AI ───────────────────────────────────────────────
def apply_super_resolution_ai(img: Image.Image, model) -> Image.Image:
    """DRLN x4 Super Resolution"""
    import torch
    from super_image import ImageLoader

    inputs = ImageLoader.load_image(img)
    inputs = inputs.unsqueeze(0)

    with torch.no_grad():
        output = model(inputs)

    output_np = output.squeeze(0).permute(1, 2, 0).cpu().numpy()
    output_np = np.clip(output_np * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(output_np)


# ─── 2. Super Resolution بدون AI (Lanczos) ───────────────────────────────────
def apply_super_resolution_classic(img: Image.Image) -> Image.Image:
    """رفع الدقة x4 بـ Lanczos"""
    w, h = img.size
    return img.resize((w * 4, h * 4), Image.LANCZOS)


# ─── 3. Denoising ─────────────────────────────────────────────────────────────
def apply_denoising(img: Image.Image) -> Image.Image:
    """
    إزالة الضوضاء بـ Non-Local Means — الأفضل للصور الطبية
    يحافظ على الحواف ويزيل الـ speckle noise
    """
    img_np = np.array(img)

    # Non-Local Means Denoising
    denoised = cv2.fastNlMeansDenoisingColored(
        img_np,
        None,
        h=8,           # قوة إزالة الضوضاء للـ luminance
        hColor=8,      # قوة إزالة الضوضاء للـ color
        templateWindowSize=7,
        searchWindowSize=21
    )

    # Bilateral Filter إضافي للحفاظ على الحواف
    bilateral = cv2.bilateralFilter(denoised, d=9, sigmaColor=75, sigmaSpace=75)

    return Image.fromarray(bilateral)


# ─── 4. Contrast Enhancement (CLAHE) ─────────────────────────────────────────
def apply_contrast_enhancement(img: Image.Image) -> Image.Image:
    """
    CLAHE على قناة L فقط — تحسين التباين بدون تشويه الألوان
    مثالي للصور الطبية والأشعة
    """
    img_np = np.array(img)

    # تحويل لـ LAB
    lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)

    # CLAHE على قناة L فقط
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l)

    # Gamma correction لتفتيح المناطق الداكنة
    gamma = 1.2
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
    l_gamma = cv2.LUT(l_enhanced, table)

    lab_enhanced = cv2.merge([l_gamma, a, b])
    result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2RGB)

    return Image.fromarray(result)


# ─── 5. Sharpening ────────────────────────────────────────────────────────────
def apply_sharpening(img: Image.Image) -> Image.Image:
    """
    Unsharp Masking — يبرز التفاصيل الدقيقة في الأشعة الطبية
    """
    img_np = np.array(img).astype(np.float32)

    # Gaussian blur
    blurred = cv2.GaussianBlur(img_np, (0, 0), sigmaX=2.0)

    # Unsharp mask: original + weight * (original - blurred)
    sharpened = cv2.addWeighted(img_np, 1.5, blurred, -0.5, 0)
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

    # kernel إضافي للتفاصيل الدقيقة
    kernel = np.array([
        [-0.5, -1,  -0.5],
        [-1,    7,  -1],
        [-0.5, -1,  -0.5]
    ]) / 2.0
    sharpened_final = cv2.filter2D(sharpened, -1, kernel)
    sharpened_final = np.clip(sharpened_final, 0, 255).astype(np.uint8)

    return Image.fromarray(sharpened_final)


# ─── Pipeline الكامل ──────────────────────────────────────────────────────────
def full_enhancement_pipeline(img: Image.Image, use_ai: bool = True) -> tuple:
    """
    Pipeline كامل:
    1. Denoising
    2. Super Resolution (AI أو Classic)
    3. Contrast Enhancement
    4. Sharpening
    """
    method_used = []

    # Step 1: Denoising أول شيء
    img = apply_denoising(img)
    method_used.append("denoising")

    # Step 2: Super Resolution
    if use_ai:
        model = get_super_image_model()
        if model is not None:
            try:
                img = apply_super_resolution_ai(img, model)
                method_used.append("ai_super_resolution_x4")
            except Exception as e:
                print(f"⚠️ AI SR failed: {e}")
                img = apply_super_resolution_classic(img)
                method_used.append("classic_super_resolution_x4")
        else:
            img = apply_super_resolution_classic(img)
            method_used.append("classic_super_resolution_x4")
    else:
        img = apply_super_resolution_classic(img)
        method_used.append("classic_super_resolution_x4")

    # Step 3: Contrast Enhancement
    img = apply_contrast_enhancement(img)
    method_used.append("clahe_contrast")

    # Step 4: Sharpening
    img = apply_sharpening(img)
    method_used.append("unsharp_masking")

    return img, " + ".join(method_used)


# ─── Endpoint ─────────────────────────────────────────────────────────────────
@enhancement_bp.route('/api/enhance', methods=['POST'])
@jwt_required(optional=True)
def enhance_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided (field name must be "image")'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # خيار: AI أو classic (اختياري، الافتراضي AI)
    use_ai = request.form.get('use_ai', 'true').lower() != 'false'

    try:
        image_bytes = file.read()
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return jsonify({'error': 'Uploaded file is not a valid image'}), 400

    # تحويل لـ RGB
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # حفظ الأصلية
    original_buffer = io.BytesIO()
    img.save(original_buffer, format='PNG')
    original_buffer.seek(0)
    original_b64 = base64.b64encode(original_buffer.read()).decode('utf-8')

    # تصغير الإدخال للموديل فقط (يرجع x4)
    max_input = 256
    if img.width > max_input or img.height > max_input:
        img.thumbnail((max_input, max_input), Image.LANCZOS)

    # تشغيل الـ Pipeline
    try:
        enhanced_img, method_used = full_enhancement_pipeline(img, use_ai=use_ai)
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500

    # تحويل النتيجة لـ base64
    enhanced_buffer = io.BytesIO()
    enhanced_img.save(enhanced_buffer, format='PNG')
    enhanced_buffer.seek(0)
    enhanced_b64 = base64.b64encode(enhanced_buffer.read()).decode('utf-8')

    # معلومات إضافية
    orig_w, orig_h = Image.open(io.BytesIO(base64.b64decode(original_b64))).size
    enh_w, enh_h = enhanced_img.size

    return jsonify({
        'success': True,
        'method': method_used,
        'use_ai': use_ai,
        'original': f'data:image/png;base64,{original_b64}',
        'enhanced': f'data:image/png;base64,{enhanced_b64}',
        'stats': {
            'original_size': f'{orig_w}x{orig_h}',
            'enhanced_size': f'{enh_w}x{enh_h}',
            'scale_factor': f'{round(enh_w / orig_w, 1)}x'
        }
    }), 200